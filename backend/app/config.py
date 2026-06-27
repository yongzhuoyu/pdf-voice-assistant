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
# DATA_DIR is the backend's runtime working directory (vector store, per-document
# indexes) — all machine-generated and gitignored. Demo/test PDFs live in the
# top-level samples/ folder, the single place a human adds books from.
DATA_DIR = BACKEND_DIR / "data"
SAMPLES_DIR = BACKEND_DIR.parent / "samples"
TEST_PDF = SAMPLES_DIR / "sherlock-holmes.pdf"   # the fixture used by the tests
CHROMA_DIR = DATA_DIR / "chroma"  # gitignored; created on first index

# --- Document ---
# Upload limits — guard against a runaway indexing job on an enormous PDF.
MAX_UPLOAD_MB = 50       # reject files larger than this
MAX_UPLOAD_PAGES = 600   # reject books with more pages than this

# --- Keys ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# --- Models ---
# Most capable Claude model; has native citations for verifiable grounding.
ANSWER_MODEL = "claude-opus-4-8"
# Cheaper/faster model for the per-chunk contextualization step (runs once per
# chunk at index time, so cost adds up — use a small model + prompt caching).
CONTEXT_MODEL = "claude-haiku-4-5"
# How many contextualization calls to run concurrently. The per-chunk calls are
# independent, so we fan them out to cut indexing time ~15x vs sequential. Tuned
# below the API rate limit; raise if you have higher limits.
CONTEXT_CONCURRENCY = 25
# Local cross-encoder reranker (no per-query API cost).
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --- Voice (Deepgram) ---
# ASR: Nova is Deepgram's most accurate general model. TTS: Aura voice.
ASR_MODEL = "nova-2"
TTS_MODEL = "aura-asteria-en"  # natural female English voice; swappable

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


def require_deepgram_key() -> str:
    """Return the Deepgram key or raise a clear error explaining how to fix it."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is not set. Add it to backend/.env "
            "(see .env.example). Get a key at https://console.deepgram.com/."
        )
    return DEEPGRAM_API_KEY
