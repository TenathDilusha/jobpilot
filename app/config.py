import os

from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
# Smaller model used when the user turns on "Fast mode" in the UI.
OLLAMA_FAST_MODEL = os.getenv("OLLAMA_FAST_MODEL", "gemma3:1b")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
# Each page is ~10 postings and costs one SerpApi search credit.
JOB_SEARCH_PAGES = int(os.getenv("JOB_SEARCH_PAGES", "2"))

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Per-document character budget sent to the model, so CV + JD fit in the context window.
MAX_DOC_CHARS = 6000
