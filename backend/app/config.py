"""
Central config for the RAG pipeline.

Keeps every tunable knob and the API-key loading in one place, so the rest of
the code reads like plain application logic instead of sprinkling `os.getenv`
and magic numbers everywhere. Think of this as the project's `.env`-backed
settings object, like a config file in an Express app.
"""

from pathlib import Path

from dotenv import load_dotenv
import os

# Load backend/.env into the environment (no-op if the file is absent).
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# --- Paths ---
DATA_DIR = BACKEND_DIR / "data"
TEST_PDF = DATA_DIR / "sherlock.pdf"
CHROMA_DIR = DATA_DIR / "chroma"  # gitignored; created on first index

# --- Keys ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Models ---
# Most capable Claude model; has native citations for verifiable grounding.
ANSWER_MODEL = "claude-opus-4-8"
# Cheaper/faster model for the per-chunk contextualization step (runs once per
# chunk at index time, so cost adds up — use a small model + prompt caching).
CONTEXT_MODEL = "claude-haiku-4-5"
# Local cross-encoder reranker (no per-query API cost).
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --- Chunking (parent-child) ---
CHILD_CHUNK_TOKENS = 300   # small chunks: precise matching for retrieval
PARENT_CHUNK_TOKENS = 1200  # larger span fed to the LLM for context

# --- Retrieval ---
DENSE_TOP_K = 20   # candidates from vector search
BM25_TOP_K = 20    # candidates from lexical search
RRF_K = 60         # Reciprocal Rank Fusion constant (standard default)
FINAL_TOP_K = 5    # passages handed to the answer model after reranking


def require_anthropic_key() -> str:
    """Return the key or raise a clear error telling the user how to fix it."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env "
            "(see .env.example). Get a key at https://console.anthropic.com/."
        )
    return ANTHROPIC_API_KEY
