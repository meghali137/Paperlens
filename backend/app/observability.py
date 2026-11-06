import json, logging, time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from . import db

class J(logging.Formatter):
    def format(self, r):
        return json.dumps({"ts": self.formatTime(r), "level": r.levelname, "msg": r.getMessage(),
                           **getattr(r, "extra", {})})
log = logging.getLogger("paperlens")
if not log.handlers:
    h = logging.StreamHandler(); h.setFormatter(J()); log.addHandler(h); log.setLevel(logging.INFO)

REQ = Histogram("http_request_seconds", "HTTP latency", ["path", "method", "status"])
LLM_LAT = Histogram("llm_call_seconds", "LLM latency", ["kind"])
LLM_TOK = Counter("llm_tokens_total", "LLM tokens", ["kind", "dir"])
RET_LAT = Histogram("retrieval_seconds", "Retrieval latency", ["mode"])
VERIFIED = Histogram("citation_verified_ratio", "Share of quotes found verbatim in the paper",
                     buckets=[0, .25, .5, .75, .9, 1.0])

def log_llm(kind, pid, model, ms, ti, to, ok):
    LLM_LAT.labels(kind).observe(ms / 1000)
    LLM_TOK.labels(kind, "in").inc(ti); LLM_TOK.labels(kind, "out").inc(to)
    with db.conn() as c:
        c.execute("insert into llm_calls values(?,?,?,?,?,?,?,?)", (time.time(), kind, pid, model, ms, ti, to, ok))
    log.info("llm_call", extra={"extra": {"kind": kind, "paper": pid, "ms": ms, "in": ti, "out": to, "ok": ok}})

def metrics_response():
    return generate_latest(), CONTENT_TYPE_LATEST

def stats():
    with db.conn() as c:
        rows = c.execute("""select kind, count(*) n, avg(latency_ms) avg_ms, sum(in_tok) tin,
                            sum(out_tok) tout, sum(1-ok) errors from llm_calls group by kind""").fetchall()
    return [dict(r) for r in rows]
