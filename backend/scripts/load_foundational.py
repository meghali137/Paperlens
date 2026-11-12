import argparse, json, sys, time
from pathlib import Path
import httpx

LIST = Path(__file__).with_name("foundational_papers.json")

def run_one(c, p, a):
    """Add one paper and wait until it is ready. Returns (status, title, error)."""
    pid, d = p["arxiv_id"], {}
    for attempt in range(a.retries + 1):
        r = c.post("/api/papers", json={"arxiv_id": pid})
        if r.status_code != 200: return "error", "", r.text[:200]
        t0 = time.time()
        while time.time() - t0 < a.timeout:
            time.sleep(a.poll)
            d = c.get(f"/api/papers/{pid}").json()
            if d["status"] in ("ready", "error"): break
        else:
            return "timeout", d.get("title", ""), "timed out"
        if d["status"] == "ready": return "ready", d["title"], ""
        if attempt < a.retries:
            print(f"    failed ({(d.get('error') or '')[:90]}). Waiting {a.retry_wait}s, then retrying...")
            time.sleep(a.retry_wait)
    return "error", d.get("title", ""), d.get("error") or ""

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8000", help="PaperLens server address")
    ap.add_argument("--category", help="only this category, e.g. NLP, Vision, LLMs")
    ap.add_argument("--limit", type=int, help="only the first N papers (good for a test run)")
    ap.add_argument("--pause", type=float, default=8, help="seconds between papers, to respect rate limits")
    ap.add_argument("--timeout", type=int, default=900, help="max seconds to wait for one paper")
    ap.add_argument("--retries", type=int, default=1, help="retries per failed paper")
    ap.add_argument("--retry-wait", type=int, default=60, help="seconds to wait before a retry")
    ap.add_argument("--poll", type=float, default=4, help="seconds between status checks")
    ap.add_argument("--dry-run", action="store_true", help="show what would be added, change nothing")
    a = ap.parse_args()

    papers = json.loads(LIST.read_text(encoding="utf-8"))
    if a.category: papers = [p for p in papers if p["category"].lower() == a.category.lower()]
    if a.limit: papers = papers[: a.limit]
    if not papers: sys.exit("No papers match those options.")

    c = httpx.Client(base_url=a.api, timeout=60)
    try: existing = {p["id"]: p["status"] for p in c.get("/api/papers").json()}
    except httpx.HTTPError: sys.exit(f"Can't reach {a.api}. Start the server first (uvicorn app.main:app --reload).")

    done, skipped, failed, odd = 0, 0, [], []
    for i, p in enumerate(papers, 1):
        tag = f"[{i}/{len(papers)}] {p['arxiv_id']:<11} {p['name']}"
        if existing.get(p["arxiv_id"]) == "ready": print(tag, "- already ready, skipping"); skipped += 1; continue
        if a.dry_run: print(tag, "- would add"); continue
        print(tag, "- adding...", flush=True)
        status, title, err = run_one(c, p, a)
        if status == "ready":
            done += 1; print(f"    ready: {title}")
            if p["title_contains"] not in title.lower():
                odd.append((p, title)); print(f"    WARNING: expected a title containing '{p['title_contains']}'. Check the arXiv ID.")
        else:
            failed.append((p, err)); print(f"    {status.upper()}: {err[:160]}")
        time.sleep(a.pause)

    print(f"\nFinished. added: {done}, skipped: {skipped}, failed: {len(failed)}")
    for p, e in failed: print(f"  FAILED  {p['arxiv_id']} {p['name']}: {e[:120]}")
    for p, t in odd: print(f"  CHECK   {p['arxiv_id']} {p['name']} -> got '{t}'")
    if failed: print("Re-run the same command to retry the failed ones (finished papers are skipped).")
    sys.exit(1 if failed else 0)

if __name__ == "__main__": main()