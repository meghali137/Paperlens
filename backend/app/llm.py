import json, random, re, time
from groq import Groq
from .config import GROQ_API_KEY, MODEL
from . import retrieval
from .observability import log_llm, VERIFIED
client = Groq(api_key=GROQ_API_KEY)

RULES = ("You are a patient AI-research teacher for university students. Use ONLY the provided excerpts. "
         "Every quote must be copied EXACTLY, character for character, from ONE excerpt (1-3 sentences) "
         "together with that excerpt's chunk number. If the excerpts do not support something, say so. Return only JSON.")

def call(kind, pid, system, user, max_tokens=3000, json_mode=False):
    """Groq chat completion (open-source model). JSON mode forces valid JSON output. Retries on rate limits."""
    t = time.time(); ok, ti, to = 1, 0, 0
    try:
        for attempt in range(3):
            try:
                kw = {"response_format": {"type": "json_object"}} if json_mode else {}
                if "gpt-oss" in MODEL: kw["reasoning_effort"] = "low"  # reasoning tokens count toward the limit
                r = client.chat.completions.create(
                    model=MODEL, max_completion_tokens=max_tokens, temperature=0.2,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kw)
                ti, to = r.usage.prompt_tokens, r.usage.completion_tokens
                txt = r.choices[0].message.content or ""
                if not txt.strip(): raise ValueError("Empty response from the model")
                return txt
            except Exception:
                if attempt == 2: raise
                time.sleep(2 ** (attempt + 1))
    except Exception:
        ok = 0; raise
    finally:
        log_llm(kind, pid, MODEL, int((time.time() - t) * 1000), ti, to, ok)

def parse_json(t):
    return json.loads(t[t.index("{"): t.rindex("}") + 1])

def _n(s): return re.sub(r"\s+", " ", s.replace("\u00ad", "")).strip().lower()

def verify(passages, chunks):
    """Keep only quotes that appear verbatim in the chunk they cite; attach the page number."""
    by = {c["id"]: c for c in chunks}; ok = []
    for p in passages:
        c = by.get(p.get("chunk")); q = _n(p.get("quote", ""))
        if c and len(q) > 20 and q in _n(c["text"]):
            ok.append({**p, "page": c["page"]})
    return ok

def ctx(chunks):
    return "\n\n".join(f"[C{c['id']} | page {c['page']}]\n{c['text']}" for c in chunks)

SEC = {
 "why": ("motivation, problem this paper aims to solve, goals", "Why was this paper made? What problem motivated it? 2-4 sentences."),
 "prev_drawbacks": ("limitations of previous approaches, existing methods fall short, prior work", "What drawbacks of the previous work led to this paper? 2-4 sentences."),
 "highlights": ("main contributions, proposed method, key results", "The key ideas and results as 3-5 short lines separated by newlines."),
 "drawbacks": ("limitations, weaknesses, failure cases, future work", "What are the drawbacks or limitations of THIS paper? 2-4 sentences."),
}
SCHEMA = '{"text": str (plain student language), "stated_in_paper": bool (false if you had to infer it), "evidence": [{"chunk": int, "quote": str}] (1-3 items)}'

def summarize(pid, meta):
    out = {"one_line": call("one_line", pid, "Return only plain text.",
           f"Title: {meta['title']}\nAbstract: {meta['abstract']}\nIn ONE plain sentence for a student: what does this paper do?", 600).strip()}
    for k, (q, ask) in SEC.items():
        ch = retrieval.search(pid, q + " " + meta["title"], "hybrid_rerank", 7)
        raw = call("summary_" + k, pid, RULES, f"Paper: {meta['title']}\n\nExcerpts:\n{ctx(ch)}\n\nTask: {ask}\nJSON schema: {SCHEMA}", json_mode=True)
        d = parse_json(raw); d["evidence"] = verify(d.get("evidence", []), ch); out[k] = d
    return out

def explain(pid, question, title):
    q = question.strip() or f"the main idea, method and key results of {title}"
    ch = retrieval.search(pid, q, "hybrid_rerank", 8)
    raw = call("explain", pid, RULES,
        f"Paper: {title}\nStudent request: {q}\n\nExcerpts:\n{ctx(ch)}\n\n"
        "Pick the 4-6 most important lines from the excerpts that answer the request.\n"
        'JSON schema: {"overview": str, "passages": [{"chunk": int, "quote": str (exact), '
        '"explanation": str (explain THIS line simply, define terms, add a concrete example)}]}', 4000, json_mode=True)
    d = parse_json(raw); prop = d.get("passages", []); ok = verify(prop, ch)
    VERIFIED.observe(len(ok) / max(1, len(prop)))
    return {"overview": d.get("overview", ""), "passages": ok, "proposed": len(prop), "verified": len(ok),
            "retrieved": [{"id": c["id"], "page": c["page"]} for c in ch]}


QUIZ_QUERIES = ["main contribution and key idea", "motivation, problem and limitations of earlier work",
                "method and architecture details", "experiments and results", "limitations and future work"]

def quiz(pid, title):
    """Multiple-choice quiz. A question is kept only if its supporting quote is found verbatim in the paper."""
    seen, ch = set(), []
    for q in QUIZ_QUERIES:
        for c in retrieval.search(pid, q + " " + title, "hybrid_rerank", 4):
            if c["id"] not in seen: seen.add(c["id"]); ch.append(c)
    raw = call("quiz", pid, RULES,
        f"Paper: {title}\n\nExcerpts:\n{ctx(ch)}\n\n"
        "Write 7 multiple-choice questions that test whether a student understood this paper. Each has exactly 4 options "
        "with ONE correct answer; the wrong options must be plausible. Each question must be answerable from the excerpts.\n"
        'JSON schema: {"questions": [{"question": str, "options": [str, str, str, str], "answer": int (index 0-3 of the correct option), '
        '"explanation": str (why it is correct, 1-2 sentences), "chunk": int, "quote": str (exact line from that excerpt that supports the correct answer)}]}', 4000, json_mode=True)
    out = []
    for q in parse_json(raw).get("questions", []):
        try:
            opts, a = [str(o) for o in q["options"]], int(q["answer"])
            if len(opts) != 4 or not 0 <= a < 4: continue
            ev = verify([{"chunk": q.get("chunk"), "quote": q.get("quote", "")}], ch)
            if not ev: continue
            order = list(range(4)); random.shuffle(order)   # models like putting the answer in the same slot
            out.append({"question": str(q["question"]), "options": [opts[i] for i in order], "answer": order.index(a),
                        "explanation": str(q.get("explanation", "")), "evidence": {"quote": ev[0]["quote"], "page": ev[0]["page"]}})
        except Exception:
            continue
    return out[:5]