"""
Document library — multi-book support.

The original design indexed a single hard-coded book. This module lets the app
hold many books: each uploaded PDF becomes a "document" with its own id, its own
contextualized-chunk store, and its own Chroma collection. A small JSON registry
tracks every document and its indexing status.

Layout on disk:
  data/docs/registry.json          — list of all documents + status
  data/docs/<id>/source.pdf        — the uploaded PDF
  data/docs/<id>/chunks.json       — contextualized chunks for that document
  (Chroma collection "doc_<id>" holds that document's vectors)

Indexing a book is slow (~minutes; the contextualizer makes one call per chunk),
so build_document() reports progress through a callback and is meant to run in a
background thread, not inline with the upload request.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import config
from app.parser import parse_pdf
from app.chunker import chunk_book
from app.contextualizer import contextualize
from app.indexer import build_index
from app.store import save_chunks, load_chunks, document_info

DOCS_DIR = config.DATA_DIR / "docs"
REGISTRY_PATH = DOCS_DIR / "registry.json"

# Indexing status values.
STATUS_INDEXING = "indexing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


@dataclass
class DocumentRecord:
    id: str
    title: str
    status: str
    n_chapters: int = 0
    n_pages: int = 0
    progress: float = 0.0          # 0..1 during indexing
    stage: str = ""                # human-readable current step
    error: str = ""
    questions: list = field(default_factory=list)  # per-book starter questions
    content_hash: str = ""         # sha256 of the PDF, for duplicate detection
    created_at: float = field(default_factory=time.time)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return base or "book"


def _doc_dir(doc_id: str) -> Path:
    return DOCS_DIR / doc_id


# Guards every read-modify-write of the JSON registry. Background indexing
# threads update progress while the request thread creates/lists documents, so
# without this a progress write could clobber a just-created record (last writer
# wins on the whole file). Hold this around load->mutate->save.
_registry_lock = threading.RLock()


def _load_registry() -> dict[str, DocumentRecord]:
    if not REGISTRY_PATH.exists():
        return {}
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {k: DocumentRecord(**v) for k, v in raw.items()}


def _save_registry(reg: dict[str, DocumentRecord]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {k: vars(v) for k, v in reg.items()}
    # Write atomically (temp file + rename) so a crash mid-write can't corrupt
    # the registry into invalid JSON.
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


# --- public API ---

def list_documents() -> list[DocumentRecord]:
    """All documents, newest first."""
    reg = _load_registry()
    return sorted(reg.values(), key=lambda d: d.created_at, reverse=True)


def get_document(doc_id: str) -> DocumentRecord | None:
    return _load_registry().get(doc_id)


def update_record(doc_id: str, **changes) -> None:
    with _registry_lock:
        reg = _load_registry()
        rec = reg.get(doc_id)
        if not rec:
            return
        for k, v in changes.items():
            setattr(rec, k, v)
        reg[doc_id] = rec
        _save_registry(reg)


def find_by_content_hash(content_hash: str) -> DocumentRecord | None:
    """Return an existing document with the same PDF content, if any."""
    for rec in _load_registry().values():
        if rec.content_hash and rec.content_hash == content_hash:
            return rec
    return None


def delete_document(doc_id: str) -> bool:
    """
    Remove a document: its registry entry, stored files, and Chroma collection.
    Returns True if it existed.
    """
    import shutil
    with _registry_lock:
        reg = _load_registry()
        if doc_id not in reg:
            return False
        del reg[doc_id]
        _save_registry(reg)
    # Drop the Chroma collection for this document.
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        client.delete_collection(f"doc_{doc_id}")
    except Exception:
        pass
    ddir = _doc_dir(doc_id)
    if ddir.exists():
        shutil.rmtree(ddir, ignore_errors=True)
    return True


def create_document(pdf_bytes: bytes, filename: str, title: str | None = None) -> str:
    """
    Register a new document and save its PDF. Returns the new document id.
    Indexing is started separately (build_document), typically in a thread.
    """
    import hashlib
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    doc_id = f"{_slugify(filename)}-{uuid.uuid4().hex[:8]}"
    ddir = _doc_dir(doc_id)
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "source.pdf").write_bytes(pdf_bytes)

    # A readable title from the original filename, used until parsing finds a
    # better one (PDF metadata). "the_red_room.pdf" -> "The Red Room".
    nice_name = Path(filename).stem.replace("_", " ").replace("-", " ").strip().title()

    with _registry_lock:
        reg = _load_registry()
        reg[doc_id] = DocumentRecord(
            id=doc_id,
            title=title or nice_name or "Untitled Document",
            status=STATUS_INDEXING,
            stage="queued",
            content_hash=content_hash,
        )
        _save_registry(reg)
    return doc_id


def build_document(doc_id: str, on_progress: Callable[[str, float], None] | None = None) -> None:
    """
    Run the full indexing pipeline for a document: parse -> chunk -> contextualize
    -> index -> persist. Updates the registry with progress and final status.
    Designed to run in a background thread.
    """
    ddir = _doc_dir(doc_id)
    pdf_path = ddir / "source.pdf"

    def progress(stage: str, frac: float):
        update_record(doc_id, stage=stage, progress=round(frac, 3))
        if on_progress:
            on_progress(stage, frac)

    # The PDF was saved as source.pdf, so its filename can't supply a title.
    # Pass the title captured at upload time (from the original filename) as the
    # fallback; parse_pdf still prefers the PDF's embedded metadata title if any.
    rec = get_document(doc_id)
    fallback_title = rec.title if rec else None

    # Stage labels are shown to the user in the progress UI — keep them plain,
    # no internal jargon (chunks, index, etc.).
    try:
        progress("Reading the book", 0.05)
        book = parse_pdf(pdf_path, fallback_title=fallback_title)

        progress("Reading the book", 0.15)
        chunked = chunk_book(book)

        progress("Studying the text", 0.25)
        _contextualize_with_progress(book, chunked, doc_id, progress)

        progress("Almost ready", 0.92)
        save_chunks(chunked, ddir / "chunks.json")
        build_index(chunked, document_id=doc_id)

        # Tailored starter questions for this book (best-effort; never fatal).
        from app.suggestions import generate_starter_questions
        questions = generate_starter_questions(book.title, chunked)

        info = document_info_for(doc_id, chunked, book.title, book.n_pages)
        update_record(
            doc_id,
            status=STATUS_READY,
            stage="ready",
            progress=1.0,
            title=book.title,
            n_chapters=info["n_chapters"],
            n_pages=info["n_pages"],
            questions=questions,
        )
    except Exception as e:  # noqa: BLE001 — surface any indexing failure to the user
        update_record(doc_id, status=STATUS_FAILED, stage="failed", error=str(e))


def recover_orphaned_jobs() -> None:
    """
    On startup, mark any document still 'indexing' as failed. Indexing runs in a
    background thread; if the server restarted mid-index, that thread is gone and
    the job will never complete or report failure on its own. Without this the UI
    would poll a stuck 'indexing' document forever.
    """
    with _registry_lock:
        reg = _load_registry()
        changed = False
        for rec in reg.values():
            if rec.status == STATUS_INDEXING:
                rec.status = STATUS_FAILED
                rec.stage = "failed"
                rec.error = "indexing was interrupted by a server restart"
                changed = True
        if changed:
            _save_registry(reg)


def load_document(doc_id: str):
    """Load a ready document's chunks + index for querying."""
    from app.indexer import load_index
    chunked = load_chunks(_doc_dir(doc_id) / "chunks.json")
    index = load_index(chunked, document_id=doc_id)
    return chunked, index


def document_info_for(doc_id: str, chunked, title: str, n_pages: int) -> dict:
    """Document metadata for the /document response (per-document)."""
    info = document_info(chunked)
    info["title"] = title
    info["n_pages"] = n_pages
    return info


# --- internals ---

def _contextualize_with_progress(book, chunked, doc_id, progress) -> None:
    """
    Run the contextualizer, mapping per-chunk completion onto the 0.25..0.9
    progress band so the upload UI shows real, steady movement during the slow
    step (one API call per chunk). Throttle registry writes to every few chunks.
    """
    lo, hi = 0.25, 0.9

    def on_chunk(done: int, total: int):
        if done % 5 == 0 or done == total:
            frac = lo + (hi - lo) * (done / max(total, 1))
            progress(f"Studying the text ({done}/{total} passages)", frac)

    contextualize(book, chunked, progress=False, on_chunk=on_chunk)
