import os, sqlite3
from .config import DATA_DIR
os.makedirs(DATA_DIR, exist_ok=True)
PATH = os.path.join(DATA_DIR, "paperlens.db")
SCHEMA = """
create table if not exists papers(id text primary key, title text, authors text, abstract text,
  year int, summary_json text, status text, error text);
create table if not exists chunks(id integer primary key autoincrement, paper_id text, idx int,
  page int, text text, emb blob);
create index if not exists chunks_paper on chunks(paper_id);
create table if not exists figures(paper_id text, path text, page int, caption text);
create table if not exists llm_calls(ts real, kind text, paper_id text, model text,
  latency_ms int, in_tok int, out_tok int, ok int);
"""
def conn():
    c = sqlite3.connect(PATH)
    c.row_factory = sqlite3.Row
    return c
def init():
    with conn() as c:
        c.executescript(SCHEMA)
