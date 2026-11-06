import json, os, time, uuid
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import DATA_DIR
from . import db, ingest, llm, retrieval
from .observability import REQ, log, metrics_response, stats

db.init()
app = FastAPI(title="PaperLens")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class AddReq(BaseModel): arxiv_id: str
class ExplainReq(BaseModel): question: str = ""

@app.middleware("http")
async def observe(request: Request, call_next):
    rid, t = uuid.uuid4().hex[:8], time.time()
    resp = await call_next(request); dt = time.time() - t
    path = getattr(request.scope.get("route"), "path", request.url.path)
    REQ.labels(path, request.method, resp.status_code).observe(dt)
    log.info("request", extra={"extra": {"rid": rid, "path": request.url.path, "status": resp.status_code, "ms": int(dt * 1000)}})
    resp.headers["x-request-id"] = rid
    return resp

def get(pid):
    with db.conn() as c: return c.execute("select * from papers where id=?", (pid,)).fetchone()
def set_status(pid, status, error=None):
    with db.conn() as c: c.execute("update papers set status=?, error=? where id=?", (status, error, pid))

def pub(r, full=False):
    s = json.loads(r["summary_json"] or "{}")
    d = {"id": r["id"], "title": r["title"], "authors": r["authors"], "year": r["year"],
         "status": r["status"], "error": r["error"], "one_line": s.get("one_line", "")}
    if full:
        with db.conn() as c:
            figs = c.execute("select path,page,caption from figures where paper_id=?", (r["id"],)).fetchall()
        d.update(abstract=r["abstract"], summary=s,
                 figures=[{"url": "/figures/" + f["path"], "page": f["page"], "caption": f["caption"]} for f in figs])
    return d

def process(pid):
    try:
        meta = ingest.fetch_meta(pid)
        with db.conn() as c:
            c.execute("update papers set title=?,authors=?,abstract=?,year=? where id=?",
                      (meta["title"], meta["authors"], meta["abstract"], meta["year"], pid))
        set_status(pid, "indexing")
        ingest.store_chunks(pid, ingest.download_pdf(pid)); retrieval.invalidate(pid)
        set_status(pid, "summarizing")
        summary = llm.summarize(pid, meta)
        with db.conn() as c: c.execute("update papers set summary_json=? where id=?", (json.dumps(summary), pid))
        set_status(pid, "ready")
    except Exception as e:
        log.error("process_failed", extra={"extra": {"paper": pid, "err": str(e)[:300]}})
        set_status(pid, "error", str(e)[:300])

@app.get("/api/papers")
def papers():
    with db.conn() as c: rows = c.execute("select * from papers order by year, title").fetchall()
    return [pub(r) for r in rows]

@app.post("/api/papers")
def add(req: AddReq, bg: BackgroundTasks):
    pid = ingest.resolve(req.arxiv_id)
    if not pid: raise HTTPException(404, "Couldn't find that paper on arXiv. Try its arXiv ID, e.g. 1706.03762.")
    with db.conn() as c:
        c.execute("insert or ignore into papers(id,title,status) values(?,?,?)", (pid, pid, "queued"))
    if get(pid)["status"] in ("queued", "error"): bg.add_task(process, pid)
    return {"id": pid}

@app.get("/api/papers/{pid:path}/search")
def debug_search(pid: str, q: str, mode: str = "hybrid_rerank", k: int = 6):
    return retrieval.search(pid, q, mode, k)

@app.post("/api/explain/{pid:path}")
def explain(pid: str, req: ExplainReq):
    r = get(pid)
    if not r or r["status"] != "ready": raise HTTPException(409, "Paper is not ready yet")
    return llm.explain(pid, req.question, r["title"])

@app.get("/api/papers/{pid:path}")
def paper(pid: str):
    r = get(pid)
    if not r: raise HTTPException(404, "Not found")
    return pub(r, full=True)

@app.delete("/api/papers/{pid:path}")
def delete(pid: str):
    with db.conn() as c:
        for t, col in (("papers", "id"), ("chunks", "paper_id"), ("figures", "paper_id")):
            c.execute(f"delete from {t} where {col}=?", (pid,))
    retrieval.invalidate(pid); return {"ok": True}

@app.get("/api/stats")
def api_stats(): return stats()

@app.get("/metrics")
def metrics():
    body, ctype = metrics_response(); return Response(body, media_type=ctype)

os.makedirs(os.path.join(DATA_DIR, "figures"), exist_ok=True)
app.mount("/figures", StaticFiles(directory=os.path.join(DATA_DIR, "figures")), name="figures")
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "..", "frontend"), html=True), name="ui")
