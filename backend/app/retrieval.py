"""Hybrid retrieval inside one paper: BM25 + dense embeddings, fused with RRF, optional cross-encoder rerank."""
import re, time
from functools import lru_cache
import numpy as np
from rank_bm25 import BM25Okapi
from .config import EMBED_MODEL, RERANK_MODEL, USE_RERANK
from . import db
from .observability import RET_LAT

def _tok(s): return re.findall(r"[a-z0-9]+", s.lower())

@lru_cache(1)
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)

@lru_cache(1)
def _reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RERANK_MODEL)

def embed(texts, query=False):
    if query:  # bge models want this prefix for queries
        texts = ["Represent this sentence for searching relevant passages: " + t for t in texts]
    return np.asarray(_embedder().encode(texts, normalize_embeddings=True), dtype="float32")

class Index:
    def __init__(self, pid):
        with db.conn() as c:
            rows = c.execute("select id,page,text,emb from chunks where paper_id=? order by idx", (pid,)).fetchall()
        self.rows = [dict(id=r["id"], page=r["page"], text=r["text"]) for r in rows]
        self.emb = np.vstack([np.frombuffer(r["emb"], dtype="float32") for r in rows]) if rows else None
        self.bm25 = BM25Okapi([_tok(r["text"]) for r in self.rows]) if rows else None

_cache = {}
def index(pid):
    if pid not in _cache: _cache[pid] = Index(pid)
    return _cache[pid]
def invalidate(pid): _cache.pop(pid, None)

def _ranks(scores):
    order = np.argsort(-scores); r = np.empty(len(scores), int); r[order] = np.arange(len(scores)); return r

def search(pid, q, mode="hybrid_rerank", k=6):
    """mode: bm25 | dense | hybrid | hybrid_rerank"""
    t0 = time.time(); ix = index(pid)
    if not ix.rows: return []
    b = ix.bm25.get_scores(_tok(q)); d = ix.emb @ embed([q], True)[0]
    s = b if mode == "bm25" else d if mode == "dense" else 1 / (60 + _ranks(b)) + 1 / (60 + _ranks(d))
    top = np.argsort(-s)[: 25 if mode == "hybrid_rerank" else k]
    if mode == "hybrid_rerank" and USE_RERANK:
        rs = _reranker().predict([(q, ix.rows[i]["text"]) for i in top])
        top = top[np.argsort(-rs)]
    RET_LAT.labels(mode).observe(time.time() - t0)
    return [{**ix.rows[i], "bm25": float(b[i]), "dense": float(d[i]), "fused": float(s[i])} for i in top[:k]]
