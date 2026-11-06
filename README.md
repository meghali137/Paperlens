# PaperLens
Run:
    cd backend && python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt && cp .env.example .env   # add GROQ_API_KEY (free key at console.groq.com)
    uvicorn app.main:app --reload
Open http://localhost:8000, add an arXiv ID (e.g. 1706.03762).
Benchmark: python -m bench.benchmark [--faithfulness]    Metrics: /metrics    LLM stats: /api/stats
