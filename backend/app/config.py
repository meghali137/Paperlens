import os
from dotenv import load_dotenv
load_dotenv()
DATA_DIR = os.getenv("DATA_DIR", "data")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
USE_RERANK = os.getenv("USE_RERANK", "1") == "1"
