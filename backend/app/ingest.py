import os, re, httpx, fitz
import xml.etree.ElementTree as ET
from .config import DATA_DIR
from . import db, retrieval
NS = {"a": "http://www.w3.org/2005/Atom"}

def norm_id(x):
    x = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", x.strip()).replace(".pdf", "")
    return re.sub(r"v\d+$", "", x)
def safe(pid): return pid.replace("/", "_")

ID_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Za-z]{2})?/\d{7})$")

def resolve(text):
    """Accept an arXiv ID, an arXiv URL or a paper title; return a clean arXiv ID, or None."""
    pid = norm_id(text)
    if ID_RE.match(pid): return pid
    for field in ("ti", "all"):
        r = httpx.get("https://export.arxiv.org/api/query", timeout=30, follow_redirects=True,
                      params={"search_query": f'{field}:"{text.strip()}"', "max_results": 1})
        e = ET.fromstring(r.text).find("a:entry", NS)
        if e is not None and e.find("a:published", NS) is not None:
            return norm_id(e.find("a:id", NS).text)
    return None

def fetch_meta(pid):
    r = httpx.get("https://export.arxiv.org/api/query", params={"id_list": pid}, timeout=30, follow_redirects=True)
    e = ET.fromstring(r.text).find("a:entry", NS)
    if e is None or e.find("a:published", NS) is None:
        raise ValueError("arXiv paper not found. Use an arXiv ID like 1706.03762 or the exact title.")
    return {"title": " ".join(e.find("a:title", NS).text.split()),
            "authors": ", ".join(a.find("a:name", NS).text for a in e.findall("a:author", NS)),
            "abstract": " ".join(e.find("a:summary", NS).text.split()),
            "year": int(e.find("a:published", NS).text[:4])}

def download_pdf(pid):
    d = os.path.join(DATA_DIR, "pdfs"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, safe(pid) + ".pdf")
    if not os.path.exists(p):
        r = httpx.get(f"https://arxiv.org/pdf/{pid}", timeout=90, follow_redirects=True); r.raise_for_status()
        open(p, "wb").write(r.content)
    return p

def chunk_pages(doc, size=900):
    out = []
    for pno, page in enumerate(doc, 1):
        text = re.sub(r"(?<=\w)-\n(?=\w)", "", page.get_text("text"))
        text = " ".join(text.split())
        sents, cur = re.split(r"(?<=[.!?])\s+", text), []
        for s in sents:
            cur.append(s)
            if sum(len(x) for x in cur) > size:
                out.append({"page": pno, "text": " ".join(cur)}); cur = cur[-1:]  # 1-sentence overlap
        if cur and (not out or out[-1]["page"] != pno or len(" ".join(cur)) > 150):
            out.append({"page": pno, "text": " ".join(cur)})
    return out

def extract_figures(doc, pid):
    d = os.path.join(DATA_DIR, "figures", safe(pid)); os.makedirs(d, exist_ok=True); out = []
    for pno, page in enumerate(doc, 1):
        text = " ".join(page.get_text("text").split())
        caps = re.findall(r"((?:Figure|Fig\.)\s*\d+[:.]\s.{0,220}?\.)(?=\s|$)", text)
        cap, n = (caps[0] if caps else ""), 0
        for im in page.get_images(full=True):
            try:
                pix = fitz.Pixmap(doc, im[0])
                if pix.width < 200 or pix.height < 120: continue
                if pix.n - pix.alpha >= 4: pix = fitz.Pixmap(fitz.csRGB, pix)
                name = f"p{pno}_{im[0]}.png"; pix.save(os.path.join(d, name)); n += 1
                out.append({"path": f"{safe(pid)}/{name}", "page": pno, "caption": cap})
            except Exception: continue
        if caps and n == 0:  # vector figure (most arXiv diagrams): render the page instead
            name = f"p{pno}_page.png"; page.get_pixmap(dpi=110).save(os.path.join(d, name))
            out.append({"path": f"{safe(pid)}/{name}", "page": pno, "caption": cap})
    return out

def store_chunks(pid, pdf):
    doc = fitz.open(pdf); chunks = chunk_pages(doc)
    embs = retrieval.embed([c["text"] for c in chunks])
    figs = extract_figures(doc, pid)
    with db.conn() as c:
        c.execute("delete from chunks where paper_id=?", (pid,)); c.execute("delete from figures where paper_id=?", (pid,))
        for i, (ch, e) in enumerate(zip(chunks, embs)):
            c.execute("insert into chunks(paper_id,idx,page,text,emb) values(?,?,?,?,?)", (pid, i, ch["page"], ch["text"], e.tobytes()))
        for f in figs:
            c.execute("insert into figures values(?,?,?,?)", (pid, f["path"], f["page"], f["caption"]))
