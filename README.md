# PaperLens

**AI research papers, explained from the paper's own words.**

New AI papers appear every day. They are long and dense, and arXiv only gives you a PDF. PaperLens is a free site that turns a paper into a structured explanation, with the paper's own key sentences shown as proof.

Every paper page answers the same four questions:

1. **Why was this paper made?**
2. **What drawbacks of earlier work led to it?**
3. **What are the highlights** (main ideas and results)?
4. **What are this paper's own drawbacks?**

Each answer comes with quotes copied from the paper, with page numbers. The page also shows the paper's real figures and charts, and an **Explain in depth** button picks the most important lines from the paper and explains each one in simple language.

## How it works

```
arXiv ID / title
      |
      v
 fetch metadata + PDF  -->  split into chunks (with page numbers)  -->  find and crop figures
      |
      v
 index every chunk twice: keywords (BM25) + meaning (embeddings)
      |
      v
 hybrid search (BM25 + embeddings, fused, then reranked)
      |
      v
 LLM sees ONLY the retrieved excerpts  -->  writes answer + exact quotes
      |
      v
 quote checker: keep a quote only if it appears word for word in the cited chunk
      |
      v
 website: sections, verified quotes, figures, "Explain in depth"
```

Why you can trust the output:

- **Grounded.** The model only sees excerpts from the paper, not its general memory.
- **Quotes are verified.** Quotes that are not found verbatim in the paper are dropped. The page shows "5/5 quotes verified".
- **Honest about gaps.** If a drawback is not stated in the paper, the page says it was inferred.

## Tech stack

| Part | Technology |
|---|---|
| Frontend | Plain HTML, CSS, JavaScript (no build step) |
| Backend | Python, FastAPI |
| Database | SQLite (one file) |
| PDF text and figures | PyMuPDF |
| Search | BM25 (`rank-bm25`) + embeddings (`sentence-transformers`, `BAAI/bge-small-en-v1.5`), fused with Reciprocal Rank Fusion, reranked by a cross-encoder |
| LLM | Open-source model served by Groq (default `openai/gpt-oss-120b`) |
| Observability | JSON logs, Prometheus metrics, per-call LLM stats |

## Project structure

```
paperlens/
├── README.md
├── .gitignore
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js                      # library page, paper page, "Explain in depth"
└── backend/
    ├── requirements.txt
    ├── .env.example                # copy to .env and add your key
    ├── app/
    │   ├── main.py                 # API routes, request logging
    │   ├── ingest.py               # arXiv metadata, PDF, chunking, figure cropping
    │   ├── retrieval.py            # hybrid search + reranking
    │   ├── llm.py                  # summaries, deep explanations, quote verification
    │   ├── observability.py        # logs and metrics
    │   ├── db.py                   # SQLite schema
    │   └── config.py               # settings from .env
    ├── bench/
    │   ├── benchmark.py            # retrieval and citation benchmark
    │   └── golden.jsonl            # test questions
    └── scripts/
        ├── load_foundational.py    # loads the 50 foundational papers
        └── foundational_papers.json
```

## Setup

You need Python 3.10 or newer and a free Groq API key from <https://console.groq.com>.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Open `.env` and set your key:

```
GROQ_API_KEY=your-groq-key
LLM_MODEL=openai/gpt-oss-120b
```

`sentence-transformers` installs PyTorch, so the install is large (a few GB). The first paper you add also downloads the search models (a few hundred MB), so the first run is slow.

## Run

Start the server **from the `backend` folder**:

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The backend serves the frontend itself, so there is nothing else to start.

## Using it

- **Add one paper:** type an arXiv ID (`1706.03762`), an arXiv link, or an exact title, then click Add. Processing takes about one to two minutes. The card shows its progress and the page updates itself.
- **Quick start:** the chips under the search box add six well-known papers with one click.
- **Explain in depth:** open a paper, optionally type a question, and click the button. You get the key lines from the paper, each followed by a plain-language explanation.
- **Figures look wrong or empty:** click **Refresh figures** on the paper page. This redoes only the figures, without calling the LLM.
- **Remove a paper:** click the ✕ on its card. A failed card also has a Retry button.

## Load the 50 foundational papers

The list lives in `backend/scripts/foundational_papers.json`: 50 papers in 8 groups (training basics, vision, multimodal, generative models, NLP, LLMs, reinforcement learning, self-supervised and graphs).

With the server running, open a **second terminal**, activate the same virtual environment, and run from `backend`:

```bash
python scripts/load_foundational.py --limit 3     # test run with 3 papers first
python scripts/load_foundational.py               # then all 50
```

What the script does:

- Adds papers one at a time and waits for each to finish. This keeps you under Groq's rate limits and is polite to arXiv.
- Skips papers that are already ready, so you can stop it (Ctrl+C) and run it again at any time.
- Retries a failed paper once after 60 seconds, which usually fixes a rate-limit error.
- Compares each downloaded title with what it expects and prints a **WARNING** if a paper does not match, which would mean a wrong arXiv ID in the list.
- Prints a summary at the end and lists what failed. Re-run the same command to retry only those.

Useful options:

| Option | Meaning |
|---|---|
| `--category NLP` | only one group (`Vision`, `LLMs`, `Generative`, ...) |
| `--limit 5` | only the first 5 papers |
| `--dry-run` | show what would be added, change nothing |
| `--pause 15` | wait longer between papers (use this if you hit rate limits) |
| `--api http://host:8000` | server address, if it is not local |

Each paper makes 5 LLM calls, so all 50 means about 250 calls and will take a while. Expect one to two hours or more on a free tier. You can leave it running. To add your own papers, add entries to `foundational_papers.json` (`category`, `name`, `arxiv_id`, `title_contains`). `title_contains` is a lowercase phrase that must appear in the real arXiv title; it is only used for the sanity check.

## API

| Method and path | Purpose |
|---|---|
| `GET /api/papers` | list papers with status |
| `POST /api/papers` | add a paper: `{"arxiv_id": "1706.03762"}` (ID, link or title) |
| `GET /api/papers/{id}` | full paper: summary, evidence, figures |
| `DELETE /api/papers/{id}` | remove a paper |
| `POST /api/explain/{id}` | deep explanation: `{"question": "..."}` (optional) |
| `POST /api/papers/{id}/figures/rebuild` | redo the figures from the stored PDF |
| `GET /api/papers/{id}/search?q=...&mode=...` | debug retrieval (`bm25`, `dense`, `hybrid`, `hybrid_rerank`) |
| `GET /api/stats` | LLM calls, average latency, tokens, errors |
| `GET /metrics` | Prometheus metrics |

## Benchmark

From `backend`, with at least one paper added:

```bash
python -m bench.benchmark                    # Recall@k and MRR for each search method
python -m bench.benchmark --faithfulness     # also measures how often LLM quotes are verbatim (uses LLM calls)
```

`bench/golden.jsonl` has only 4 starter questions for one paper. Add 30 or more per paper before trusting the numbers. A line looks like: `{"paper_id": "1706.03762", "question": "...", "gold": ["phrase that must be in the right chunk"]}`.

## Observability

- Logs are JSON lines on the terminal (request id, path, status, time; one line per LLM call).
- `/metrics` exposes HTTP latency, LLM latency and tokens, retrieval time, and the share of quotes that were verified.
- `/api/stats` summarizes LLM usage per call type.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run `uvicorn` from the `backend` folder, not the project root. |
| `model ... does not exist or you do not have access to it` | Set `LLM_MODEL` in `.env` to a model your Groq key can use (default `openai/gpt-oss-120b`) and restart. Groq's model list changes; see <https://console.groq.com/docs/models>. |
| A card says "Failed" right after adding a title | Use the arXiv ID, or the exact paper title. Delete the card with ✕ and add it again. |
| Page is blank at `127.0.0.1:5500` | That is a dev server. Use <http://127.0.0.1:8000> (the frontend also works from other ports and calls the API on port 8000). |
| Figures are black, missing or badly cropped | Click **Refresh figures**. Some papers still crop imperfectly. |
| Rate-limit (429) errors | Wait a minute and retry. When loading many papers, use `--pause 15`. |
| A paper is stuck on "Indexing" or "Writing summary" after a server restart | Delete it with ✕ and add it again. |
| Changed `.env` but nothing changes | Restart the server. Settings are read at startup. |

## Limitations

- Equations and tables extract poorly from PDFs. Figure cropping is a heuristic.
- Open-source models sometimes paraphrase a quote instead of copying it. The checker drops those, so you may see "3/5 verified" on some pages.
- The benchmark set is tiny.
- LLM explanations can still contain mistakes. Always compare them with the quoted source lines.
- No user accounts, and no protection against abuse yet. It is built for local use. Add authentication and rate limiting before putting it on the public internet.

## Roadmap

- Larger benchmark and model comparison.
- Concept pages (attention, RLHF, diffusion) that link papers into a learning path.
- Daily digest of important new papers.
- Better figure and equation extraction (arXiv HTML versions, GROBID).
- Public deployment.
