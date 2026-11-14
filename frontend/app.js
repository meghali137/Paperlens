// Works whether you open the site via the backend (port 8000) or a dev server like VS Code Live Server.
const API = location.port === "8000" ? "" : "http://127.0.0.1:8000";
const $ = s => document.querySelector(s);
const esc = s => (s || "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const J = {"Content-Type": "application/json"};
let timer, CUR = null, GL = {}, GRX = null, PAPERS = [], F = {q: "", cat: "All"};

async function api(u, o) {
  const r = await fetch(API + u, o);
  if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail || m; } catch {} throw new Error(typeof m === "string" ? m.slice(0, 300) : "Request failed"); }
  return r.json();
}

async function loadCur() {
  if (CUR) return CUR;
  try { CUR = await api("/api/curriculum"); } catch { CUR = {papers: {}, prereqs: {}, paths: [], glossary: {}}; }
  GL = {}; for (const [t, d] of Object.entries(CUR.glossary)) GL[t.toLowerCase()] = d;
  const ts = Object.keys(GL).sort((a, b) => b.length - a.length).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  GRX = ts.length ? new RegExp("\\b(" + ts.join("|") + ")(?:s|es)?\\b", "gi") : null;
  return CUR;
}

function gloss(html) {
  if (!GRX) return html;
  const seen = new Set();
  return html.replace(GRX, (m, t) => { const k = t.toLowerCase(); if (seen.has(k)) return m; seen.add(k);
    return `<span class="g" tabindex="0" data-d="${esc(GL[k])}">${m}</span>`; });
}
const catOf = p => ((CUR && CUR.papers[p.id]) || {}).category || "Other";
const nameOf = id => ((CUR && CUR.papers[id]) || {}).name || id;
const getRead = () => { try { return new Set(JSON.parse(localStorage.getItem("pl_read") || "[]")); } catch { return new Set(); } };
const setRead = s => { try { localStorage.setItem("pl_read", JSON.stringify([...s])); } catch {} };

const LABEL = {queued: "Queued", indexing: "Indexing PDF", summarizing: "Writing summary", ready: "Ready", error: "Failed"};
const stCls = s => s === "ready" ? "ready" : s === "error" ? "error" : "busy";
const CHIPS = [["Attention Is All You Need", "1706.03762"], ["BERT", "1810.04805"], ["ResNet", "1512.03385"], ["GPT-3", "2005.14165"], ["Adam", "1412.6980"], ["GANs", "1406.2661"]];

async function home() {
  clearTimeout(timer); await loadCur();
  $("#view").innerHTML = `<section class="hero">
    <h1 class="serif">Understand any AI paper <em>in minutes.</em></h1>
    <p class="lead">Paste an arXiv ID or a title. Get why it was written, what it fixed, where it falls short, with the paper’s own key lines.</p>
    <div class="addbox"><input id="aid" placeholder="arXiv ID or paper title, e.g. 1706.03762"><button class="btn" id="addb">Add paper</button></div>
    <div class="chips">${CHIPS.map(([n, id]) => `<button class="chip" data-id="${id}">${n}</button>`).join("")}</div>
    <div class="msg" id="msg"></div>
    <div class="feat"><div><small>Why it was made</small><p>The problem that pushed the authors to write it.</p></div>
    <div><small>What it fixed</small><p>The drawbacks of earlier work this paper responds to.</p></div>
    <div><small>Where it falls short</small><p>Its own limitations, marked when inferred.</p></div></div></section>
    <h2 class="serif sec">Library</h2>
    <div class="filters"><input id="fs" placeholder="Search papers by title, author or topic…" value="${esc(F.q)}"><div id="cats" class="cats"></div></div>
    <div id="list" class="grid"></div>`;
  $("#addb").onclick = () => add($("#aid").value);
  $("#aid").onkeydown = e => { if (e.key === "Enter") add($("#aid").value); };
  document.querySelectorAll(".chip").forEach(c => c.onclick = () => add(c.dataset.id));
  $("#fs").oninput = e => { F.q = e.target.value; renderList(); };
  $("#cats").onclick = e => { const b = e.target.closest("[data-cat]"); if (b) { F.cat = b.dataset.cat; renderList(); } };
  $("#list").onclick = onList;
  refresh();
}

async function add(v) {
  const msg = $("#msg"); if (!v.trim()) return;
  msg.className = "msg"; msg.textContent = "Looking it up on arXiv…";
  try { await api("/api/papers", {method: "POST", headers: J, body: JSON.stringify({arxiv_id: v})});
        $("#aid").value = ""; msg.textContent = "Added. Reading and indexing the paper takes 1–2 minutes."; refresh(); }
  catch (e) { msg.className = "msg err"; msg.textContent = e.message; }
}

const card = p => `<a class="card" href="#/p/${esc(p.id)}">
  <button class="del" data-del="${esc(p.id)}" title="Remove">✕</button>
  <span class="st ${stCls(p.status)}">${LABEL[p.status] || p.status}</span><span class="tag">${esc(catOf(p))}</span>
  <h3>${esc(p.title)}</h3><div class="meta">${esc((p.authors || "").split(",").slice(0, 3).join(","))} · ${p.year || ""}</div>
  <p>${p.status === "error" ? esc(p.error) : esc(p.one_line)}</p>
  ${p.status === "error" ? `<button class="btn ghost sm retry" data-retry="${esc(p.id)}">Retry</button>` : ""}</a>`;

function renderList() {
  const list = $("#list"); if (!list) return;
  const cats = ["All", ...new Set(PAPERS.map(catOf))];
  if (!cats.includes(F.cat)) F.cat = "All";
  $("#cats").innerHTML = cats.map(c => `<button class="fchip ${c === F.cat ? "on" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  const q = F.q.trim().toLowerCase();
  const ps = PAPERS.filter(p => (F.cat === "All" || catOf(p) === F.cat) &&
    (!q || (p.title + " " + p.authors + " " + p.one_line + " " + catOf(p)).toLowerCase().includes(q)));
  list.innerHTML = ps.length ? ps.map(card).join("")
    : `<div class="empty" style="grid-column:1/-1">${PAPERS.length ? "No papers match your search." : "No papers yet. Pick one of the chips above to start."}</div>`;
}

async function refresh() {
  clearTimeout(timer); if (!$("#list")) return;
  try { PAPERS = await api("/api/papers"); }
  catch { $("#list").innerHTML = `<div class="empty" style="grid-column:1/-1">Can’t reach the backend at <code>${API || location.origin}</code>.<br>Start it with <code>uvicorn app.main:app --reload</code> from the backend folder.</div>`; return; }
  renderList();
  if (PAPERS.some(p => !["ready", "error"].includes(p.status))) timer = setTimeout(refresh, 4000);
}

async function onList(e) {
  const d = e.target.closest("[data-del]"), r = e.target.closest("[data-retry]");
  if (d) { e.preventDefault(); if (confirm("Remove this paper?")) { await api("/api/papers/" + d.dataset.del, {method: "DELETE"}); refresh(); } }
  if (r) { e.preventDefault(); await api("/api/papers", {method: "POST", headers: J, body: JSON.stringify({arxiv_id: r.dataset.retry})}); refresh(); }
}

/* ---------- paper page ---------- */
const quote = e => `<blockquote>“${esc(e.quote)}” <span>· page ${e.page}</span></blockquote>`;
const SEC = [["why", "Why this paper was made", ""], ["prev_drawbacks", "Drawbacks of the previous work that led to it", "prev"],
             ["highlights", "Highlights", "res"], ["drawbacks", "Drawbacks of this paper", "draw"]];
const sec = (s, [k, t, c]) => { const d = s[k]; if (!d) return "";
  return `<div class="box ${c}"><h3>${t}</h3><p>${gloss(esc(d.text))}</p>
  ${d.stated_in_paper === false ? '<p class="meta">Not stated explicitly in the paper; inferred from its content.</p>' : ""}
  ${(d.evidence || []).map(quote).join("")}</div>`; };

function prereqHTML(id, have) {
  const pr = (CUR.prereqs || {})[id]; if (!pr || (!pr.papers.length && !pr.concepts.length)) return "";
  const concepts = pr.concepts.map(t => `<span class="pchip g" tabindex="0" data-d="${esc(GL[t.toLowerCase()] || "")}">${esc(t)}</span>`).join("");
  const papers = pr.papers.map(x => { const h = have.get(x);
    if (h && h.status === "ready") return `<a class="pchip" href="#/p/${x}">${esc(nameOf(x))}</a>`;
    if (h && h.status !== "error") return `<span class="pchip off">${esc(nameOf(x))} · processing</span>`;
    return `<span class="pchip off">${esc(nameOf(x))} <button class="mini" data-add="${x}">Add</button></span>`; }).join("");
  return `<div class="prereq"><h3>Before you read this</h3>
    ${concepts ? `<div class="prow"><span class="lbl">Concepts</span>${concepts}</div>` : ""}
    ${papers ? `<div class="prow"><span class="lbl">Papers</span>${papers}</div>` : ""}</div>`;
}

async function paper(id) {
  clearTimeout(timer); await loadCur();
  let p, lib; try { [p, lib] = await Promise.all([api("/api/papers/" + id), api("/api/papers").catch(() => [])]); }
  catch (e) { $("#view").innerHTML = `<a class="back" href="#">← Library</a><div class="empty">${esc(e.message)}</div>`; return; }
  const have = new Map(lib.map(x => [x.id, x]));
  if (p.status !== "ready") {
    const order = ["queued", "indexing", "summarizing"], at = order.indexOf(p.status);
    $("#view").innerHTML = `<a class="back" href="#">← Library</a><h1 class="serif ptitle">${esc(p.title)}</h1>
      ${p.status === "error" ? `<div class="empty">Failed: ${esc(p.error)}</div>` :
      `<div class="steps">${["Queued", "Indexing PDF", "Writing summary"].map((n, i) => `<span class="${i < at ? "done" : i === at ? "on" : ""}">${n}</span>`).join("")}</div><p class="meta">This page updates itself.</p>`}`;
    if (p.status !== "error") timer = setTimeout(() => paper(id), 4000); return;
  }
  const s = p.summary;
  $("#view").innerHTML = `<a class="back" href="#">← Library</a><h1 class="serif ptitle">${esc(p.title)}</h1>
    <div class="meta">${esc(p.authors)} · ${p.year} · <a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener">arXiv:${esc(p.id)}</a></div>
    <p class="oneline">${gloss(esc(s.one_line))}</p>${prereqHTML(id, have)}${SEC.map(x => sec(s, x)).join("")}
    <h2 class="serif sec">Figures and charts<button class="btn ghost sm" id="refig">Refresh figures</button></h2>
    <div class="figs">${p.figures.map(f => `<figure><a href="${API}${f.url}" target="_blank" rel="noopener"><img src="${API}${f.url}" loading="lazy" alt=""></a><figcaption>Page ${f.page} · ${esc(f.caption)}</figcaption></figure>`).join("") || '<span class="meta">No figures found.</span>'}</div>
    <h2 class="serif sec">Explain in depth</h2>
    <div class="explain"><span class="meta">Pulls the key lines from the paper and explains each one. Optionally ask about a specific part.</span>
    <textarea id="q" placeholder="Optional, e.g. How does multi-head attention work?"></textarea>
    <button class="btn" id="ex">Explain in depth</button><div id="out"></div></div>
    <h2 class="serif sec">Test yourself</h2>
    <div class="explain"><span class="meta">Five questions written from this paper. Every answer is backed by a line from its text.</span><br><br>
    <button class="btn" id="qs">Start quiz</button><div id="quiz"></div></div>`;
  $("#refig").onclick = async () => { $("#refig").textContent = "Working…";
    try { await api("/api/papers/" + id + "/figures/rebuild", {method: "POST"}); } catch (e) { alert(e.message); } paper(id); };
  $("#ex").onclick = async () => {
    $("#out").innerHTML = '<p class="meta">Reading the paper…</p>';
    try { const r = await api("/api/explain/" + id, {method: "POST", headers: J, body: JSON.stringify({question: $("#q").value})});
      $("#out").innerHTML = `<p>${gloss(esc(r.overview))}</p>` + r.passages.map(x => quote(x) + `<p>${gloss(esc(x.explanation))}</p>`).join("") +
        `<p class="meta">${r.verified}/${r.proposed} quotes verified word-for-word against the paper text.</p>`;
    } catch (e) { $("#out").innerHTML = `<p class="meta" style="color:var(--red)">${esc(e.message)}</p>`; }
  };
  $("#qs").onclick = () => startQuiz(id, false);
}

/* ---------- quiz ---------- */
let QKEY = null;
async function startQuiz(id, fresh) {
  const box = $("#quiz"); $("#qs").style.display = "none";
  if (QKEY) { document.removeEventListener("keydown", QKEY); QKEY = null; }
  const retry = msg => { box.innerHTML = `<p class="meta">${msg}</p><button class="btn ghost sm" id="qretry">Try again</button>`; $("#qretry").onclick = () => startQuiz(id, true); };
  box.innerHTML = '<p class="meta">Writing questions from the paper… this takes 10–20 seconds the first time.</p>';
  let qs; try { qs = (await api(`/api/quiz/${id}${fresh ? "?fresh=1" : ""}`)).questions; } catch (e) { return retry(esc(e.message)); }
  if (!qs.length) return retry("Couldn’t produce verified questions this time.");
  const n = qs.length; let i = 0, score = 0, answered = false, res = [];
  const pick = k => { const b = box.querySelectorAll(".opt")[k]; if (b && !answered) b.click(); };
  QKEY = e => {
    if (!document.body.contains(box) || /INPUT|TEXTAREA/.test((e.target.tagName || ""))) return;
    const k = "abcd1234".indexOf(e.key.toLowerCase()) % 4;
    if (e.key.length === 1 && "abcd1234".includes(e.key.toLowerCase())) pick(k);
    else if (e.key === "Enter" && answered && $("#qn")) $("#qn").click();
  };
  document.addEventListener("keydown", QKEY);
  const done = () => {
    const pct = Math.round(100 * score / n);
    const msg = score === n ? "Perfect score. You understood this paper." : pct >= 60 ? "Good work. You got the main ideas." : "Worth another read. Try the sections you missed.";
    box.innerHTML = `<div class="qdone qbody"><div class="ring" style="--p:${pct}"><span>${score}/${n}</span></div>
      <h3>${msg}</h3><p class="meta">Every answer was backed by a line from the paper.</p>
      <div class="row"><button class="btn" id="qre">New questions</button><button class="btn ghost" id="qagain">Retry these</button></div></div>`;
    $("#qre").onclick = () => startQuiz(id, true);
    $("#qagain").onclick = () => { i = 0; score = 0; res = []; show(); };
  };
  const show = () => {
    if (i >= n) return done();
    const q = qs[i]; answered = false;
    box.innerHTML = `<div class="qbody"><div class="qhead"><div class="qdots">${qs.map((_, k) => `<i class="${k < i ? (res[k] ? "ok" : "bad") : k === i ? "cur" : ""}"></i>`).join("")}</div>
      <span class="meta">Question ${i + 1} of ${n}</span></div>
      <h3 class="qq">${gloss(esc(q.question))}</h3>
      <div class="qopts">${q.options.map((o, k) => `<button class="opt" data-k="${k}"><b class="ltr">${"ABCD"[k]}</b><span>${esc(o)}</span><em class="mk"></em></button>`).join("")}</div>
      <div id="qfb"></div></div>`;
    box.querySelectorAll(".opt").forEach(b => b.onclick = () => {
      if (answered) return; answered = true;
      const ok = +b.dataset.k === q.answer; if (ok) score++; res[i] = ok;
      box.querySelectorAll(".opt").forEach(x => { x.disabled = true; const k = +x.dataset.k;
        if (k === q.answer) { x.classList.add("right"); x.querySelector(".mk").textContent = "✓"; }
        else if (x === b) { x.classList.add("wrong"); x.querySelector(".mk").textContent = "✕"; }
        else x.classList.add("dim"); });
      box.querySelectorAll(".qdots i")[i].className = ok ? "ok" : "bad";
      $("#qfb").innerHTML = `<div class="fb ${ok ? "good" : "bad"}"><span class="fbt">${ok ? "Correct" : "Not quite"}</span>
        <p>${gloss(esc(q.explanation))}</p>
        <div class="src"><span class="srcl">From the paper · page ${q.evidence.page}</span><p>“${esc(q.evidence.quote)}”</p></div></div>
        <div class="qnav"><span class="meta">Score ${score} of ${i + 1}</span><button class="btn" id="qn">${i + 1 < n ? "Next question →" : "See score →"}</button></div>`;
      $("#qn").onclick = () => { i++; show(); };
    });
  };
  show();
}

/* ---------- learning paths ---------- */
async function paths() {
  clearTimeout(timer); const c = await loadCur();
  const lib = await api("/api/papers").catch(() => []); const have = new Map(lib.map(p => [p.id, p]));
  const read = getRead(); let busy = false;
  const act = id => { const h = have.get(id);
    if (!h) return `<button class="btn ghost sm" data-add="${id}">Add to library</button>`;
    if (h.status === "ready") return `<a class="btn sm" href="#/p/${id}">Open</a>`;
    if (h.status === "error") return `<button class="btn ghost sm" data-add="${id}">Retry</button>`;
    busy = true; return `<span class="st busy">${LABEL[h.status] || h.status}</span>`; };
  $("#view").innerHTML = `<section class="phead"><h1 class="serif ptitle">Learning paths</h1>
    <p class="lead2">Papers build on each other. Follow a path in order, tick what you have read, and add any paper you do not have yet.</p></section>` +
    c.paths.map(p => { const n = p.steps.filter(s => read.has(s.id)).length;
      return `<section class="path"><div class="phd"><h2>${esc(p.title)}</h2><span class="meta">${n} of ${p.steps.length} read</span></div>
        <p class="meta">${esc(p.blurb)}</p><div class="bar"><i style="width:${100 * n / p.steps.length}%"></i></div>
        <ol class="steps2">${p.steps.map(s => `<li><label class="chk"><input type="checkbox" data-read="${s.id}" ${read.has(s.id) ? "checked" : ""}></label>
          <div><b>${esc(nameOf(s.id))}</b><p>${gloss(esc(s.why))}</p></div>${act(s.id)}</li>`).join("")}</ol></section>`; }).join("");
  if (busy) timer = setTimeout(paths, 5000);
}

/* ---------- routing and shared click actions ---------- */
async function onAct(e) {
  const a = e.target.closest("[data-add]");
  if (a) { e.preventDefault(); a.disabled = true; a.textContent = "Adding…";
    try { await api("/api/papers", {method: "POST", headers: J, body: JSON.stringify({arxiv_id: a.dataset.add})}); } catch (err) { alert(err.message); }
    render(); return; }
  const r = e.target.closest("[data-read]");
  if (r) { const s = getRead(); r.checked ? s.add(r.dataset.read) : s.delete(r.dataset.read); setRead(s); paths(); }
}
function render() {
  const h = location.hash, m = h.match(/^#\/p\/(.+)$/);
  document.querySelectorAll(".nav a[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === (h === "#/paths" ? "paths" : m ? "" : "home")));
  if (m) paper(decodeURIComponent(m[1])); else if (h === "#/paths") paths(); else home();
}
function route() { render(); window.scrollTo(0, 0); }
$("#view").addEventListener("click", onAct);
$("#navadd").onclick = () => { location.hash = ""; setTimeout(() => $("#aid") && $("#aid").focus(), 50); };
addEventListener("hashchange", route); route();