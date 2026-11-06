// Works whether you open the site via the backend (port 8000) or a dev server like VS Code Live Server.
const API = location.port === "8000" ? "" : "http://127.0.0.1:8000";
const $ = s => document.querySelector(s);
const esc = s => (s || "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const J = {"Content-Type": "application/json"};
let timer;

async function api(u, o) {
  const r = await fetch(API + u, o);
  if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail || m; } catch {} throw new Error(typeof m === "string" ? m.slice(0, 300) : "Request failed"); }
  return r.json();
}
const LABEL = {queued: "Queued", indexing: "Indexing PDF", summarizing: "Writing summary", ready: "Ready", error: "Failed"};
const stCls = s => s === "ready" ? "ready" : s === "error" ? "error" : "busy";
const CHIPS = [["Attention Is All You Need", "1706.03762"], ["BERT", "1810.04805"], ["ResNet", "1512.03385"], ["GPT-3", "2005.14165"], ["Adam", "1412.6980"], ["GANs", "1406.2661"]];

function home() {
  clearTimeout(timer);
  $("#view").innerHTML = `<section class="hero">
    <span class="pill"><b></b>Foundational AI papers, explained</span>
    <h1 class="serif">Understand any AI paper <em>in minutes.</em></h1>
    <p class="lead">Paste an arXiv ID or a title. Get why it was written, what it fixed, where it falls short, with the paper’s own key lines.</p>
    <div class="addbox"><input id="aid" placeholder="arXiv ID or paper title, e.g. 1706.03762"><button class="btn" id="addb">Add paper</button></div>
    <div class="chips">${CHIPS.map(([n, id]) => `<button class="chip" data-id="${id}">${n}</button>`).join("")}</div>
    <div class="msg" id="msg"></div>
    <div class="feat"><div><small>Why it was made</small><p>The problem that pushed the authors to write it.</p></div>
    <div><small>What it fixed</small><p>The drawbacks of earlier work this paper responds to.</p></div>
    <div><small>Where it falls short</small><p>Its own limitations, marked when inferred.</p></div></div></section>
    <h2 class="serif sec">Library</h2><div id="list" class="grid"></div>`;
  $("#addb").onclick = () => add($("#aid").value);
  $("#aid").onkeydown = e => { if (e.key === "Enter") add($("#aid").value); };
  document.querySelectorAll(".chip").forEach(c => c.onclick = () => add(c.dataset.id));
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

async function refresh() {
  clearTimeout(timer); if (!$("#list")) return;
  let ps; try { ps = await api("/api/papers"); }
  catch { $("#list").innerHTML = `<div class="empty" style="grid-column:1/-1">Can’t reach the backend at <code>${API || location.origin}</code>.<br>Start it with <code>uvicorn app.main:app --reload</code> from the backend folder.</div>`; return; }
  $("#list").innerHTML = ps.length ? ps.map(p => `<a class="card" href="#/p/${esc(p.id)}">
      <button class="del" data-del="${esc(p.id)}" title="Remove">✕</button>
      <span class="st ${stCls(p.status)}">${LABEL[p.status] || p.status}</span>
      <h3>${esc(p.title)}</h3><div class="meta">${esc((p.authors || "").split(",").slice(0, 3).join(","))} · ${p.year || ""}</div>
      <p>${p.status === "error" ? esc(p.error) : esc(p.one_line)}</p>
      ${p.status === "error" ? `<button class="btn ghost sm retry" data-retry="${esc(p.id)}">Retry</button>` : ""}</a>`).join("")
    : `<div class="empty" style="grid-column:1/-1">No papers yet. Pick one of the chips above to start.</div>`;
  if (ps.some(p => !["ready", "error"].includes(p.status))) timer = setTimeout(refresh, 4000);
}

async function onList(e) {
  const d = e.target.closest("[data-del]"), r = e.target.closest("[data-retry]");
  if (d) { e.preventDefault(); if (confirm("Remove this paper?")) { await api("/api/papers/" + d.dataset.del, {method: "DELETE"}); refresh(); } }
  if (r) { e.preventDefault(); await api("/api/papers", {method: "POST", headers: J, body: JSON.stringify({arxiv_id: r.dataset.retry})}); refresh(); }
}

const quote = e => `<blockquote>“${esc(e.quote)}” <span>· page ${e.page}</span></blockquote>`;
const SEC = [["why", "Why this paper was made", ""], ["prev_drawbacks", "Drawbacks of the previous work that led to it", "prev"],
             ["highlights", "Highlights", "res"], ["drawbacks", "Drawbacks of this paper", "draw"]];
const sec = (s, [k, t, c]) => { const d = s[k]; if (!d) return "";
  return `<div class="box ${c}"><h3>${t}</h3><p>${esc(d.text)}</p>
  ${d.stated_in_paper === false ? '<p class="meta">Not stated explicitly in the paper; inferred from its content.</p>' : ""}
  ${(d.evidence || []).map(quote).join("")}</div>`; };

async function paper(id) {
  clearTimeout(timer);
  let p; try { p = await api("/api/papers/" + id); } catch (e) { $("#view").innerHTML = `<a class="back" href="#">← Library</a><div class="empty">${esc(e.message)}</div>`; return; }
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
    <p class="oneline">${esc(s.one_line)}</p>${SEC.map(x => sec(s, x)).join("")}
    <h2 class="serif sec">Figures and charts<button class="btn ghost sm" id="refig">Refresh figures</button></h2>
    <div class="figs">${p.figures.map(f => `<figure><a href="${API}${f.url}" target="_blank" rel="noopener"><img src="${API}${f.url}" loading="lazy" alt=""></a><figcaption>Page ${f.page} · ${esc(f.caption)}</figcaption></figure>`).join("") || '<span class="meta">No figures found.</span>'}</div>
    <h2 class="serif sec">Explain in depth</h2>
    <div class="explain"><span class="meta">Pulls the key lines from the paper and explains each one. Optionally ask about a specific part.</span>
    <textarea id="q" placeholder="Optional, e.g. How does multi-head attention work?"></textarea>
    <button class="btn" id="ex">Explain in depth</button><div id="out"></div></div>`;
  $("#refig").onclick = async () => { $("#refig").textContent = "Working…";
    try { await api("/api/papers/" + id + "/figures/rebuild", {method: "POST"}); } catch (e) { alert(e.message); } paper(id); };
  $("#ex").onclick = async () => {
    $("#out").innerHTML = '<p class="meta">Reading the paper…</p>';
    try { const r = await api("/api/explain/" + id, {method: "POST", headers: J, body: JSON.stringify({question: $("#q").value})});
      $("#out").innerHTML = `<p>${esc(r.overview)}</p>` + r.passages.map(x => quote(x) + `<p>${esc(x.explanation)}</p>`).join("") +
        `<p class="meta">${r.verified}/${r.proposed} quotes verified word-for-word against the paper text.</p>`;
    } catch (e) { $("#out").innerHTML = `<p class="meta" style="color:var(--red)">${esc(e.message)}</p>`; }
  };
}

function route() { const m = location.hash.match(/^#\/p\/(.+)$/); m ? paper(decodeURIComponent(m[1])) : home(); window.scrollTo(0, 0); }
$("#navadd").onclick = () => { location.hash = ""; setTimeout(() => $("#aid") && $("#aid").focus(), 50); };
addEventListener("hashchange", route); route();