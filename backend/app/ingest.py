import os, re, shutil, httpx, fitz
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

CAP_RE = re.compile(r"^(Figure|Fig\.)\s*(\d+)\s*[:.]")

def extract_figures(doc, pid):
    """Find each 'Figure N:' caption, collect the drawings/images just above it, and render only that region.
    Rendering the region (not extracting raw images) handles vector diagrams, charts and transparent PNGs."""
    d = os.path.join(DATA_DIR, "figures", safe(pid))
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d, exist_ok=True); out = []
    for pno, page in enumerate(doc, 1):
        W, H = page.rect.width, page.rect.height
        caps = []
        for b in page.get_text("blocks"):
            t = " ".join(b[4].split()); m = CAP_RE.match(t)
            if b[6] == 0 and m: caps.append((fitz.Rect(b[:4]), t, m.group(2)))
        if not caps: continue
        gfx = []
        for dr in page.get_drawings():
            r = fitz.Rect(dr["rect"])
            if r.height > 0.8 * H or (r.width > 0.95 * W and r.height < 4): continue  # page frames / header rules
            gfx.append(fitz.Rect(r.x0 - .5, r.y0 - .5, r.x1 + .5, r.y1 + .5))
        gfx += [fitz.Rect(im["bbox"]) for im in page.get_image_info()]
        prev = 0
        for rect, t, num in sorted(caps, key=lambda c: c[0].y0):
            cand = [g for g in gfx if g.y1 <= rect.y0 + 3 and g.y0 >= prev - 3 and g.x1 > rect.x0 - 5 and g.x0 < rect.x1 + 5]
            cand.sort(key=lambda g: -g.y1); u = None
            for g in cand:                      # grow a cluster upward from the caption
                if u is None:
                    if rect.y0 - g.y1 < 90: u = fitz.Rect(g)
                elif g.y1 >= u.y0 - 45: u |= g
            prev = rect.y1
            if u is None or u.height < 30 or u.width < 40: continue
            clip = fitz.Rect(max(0, u.x0 - 16), max(0, u.y0 - 10), min(W, u.x1 + 16), rect.y0 - 1)
            name = f"fig{num}_p{pno}.png"
            page.get_pixmap(clip=clip, dpi=150).save(os.path.join(d, name))
            out.append({"path": f"{safe(pid)}/{name}", "page": pno, "caption": t[:240]})
    return out

def rebuild_figures(pid):
    figs = extract_figures(fitz.open(download_pdf(pid)), pid)
    with db.conn() as c:
        c.execute("delete from figures where paper_id=?", (pid,))
        for f in figs: c.execute("insert into figures values(?,?,?,?)", (pid, f["path"], f["page"], f["caption"]))

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