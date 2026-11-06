"""Run from backend/:  python -m bench.benchmark [--k 5] [--faithfulness]
Retrieval quality: Recall@k and MRR for bm25 / dense / hybrid / hybrid_rerank on a golden set.
A chunk is relevant if it contains any gold substring. Extend golden.jsonl with ~30+ questions per paper."""
import argparse, json, time
from app import db, llm, retrieval

def norm(s): return " ".join(s.lower().split())

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--file", default="bench/golden.jsonl"); ap.add_argument("--faithfulness", action="store_true")
    a = ap.parse_args(); db.init()
    rows = [json.loads(l) for l in open(a.file) if l.strip()]
    print(f"{'mode':15}{'recall@'+str(a.k):>10}{'mrr':>8}{'avg_ms':>9}")
    for mode in ["bm25", "dense", "hybrid", "hybrid_rerank"]:
        rec = mrr = lat = 0
        for r in rows:
            t = time.time(); res = retrieval.search(r["paper_id"], r["question"], mode, a.k); lat += time.time() - t
            hit = [any(g.lower() in norm(c["text"]) for g in r["gold"]) for c in res]
            if any(hit): rec += 1; mrr += 1 / (hit.index(True) + 1)
        n = len(rows); print(f"{mode:15}{rec/n:>10.2f}{mrr/n:>8.2f}{1000*lat/n:>9.0f}")
    if a.faithfulness:  # costs LLM calls
        ratios = []
        for r in rows:
            with db.conn() as c: t = c.execute("select title from papers where id=?", (r["paper_id"],)).fetchone()["title"]
            e = llm.explain(r["paper_id"], r["question"], t); ratios.append(e["verified"] / max(1, e["proposed"]))
        print(f"citation faithfulness (quotes found verbatim): {sum(ratios)/len(ratios):.2f}")

if __name__ == "__main__": main()
