"""
Persistence for the contextualized chunks.

Contextualizing the book costs real API calls, so we run it once and cache the
result to disk as JSON. The indexer and retriever load from here instead of
re-contextualizing on every run. Plain JSON (not a DB) keeps it inspectable —
you can open the file and read exactly what got indexed.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app import config
from app.chunker import ChunkedBook, ParentChunk, ChildChunk

CHUNKS_PATH = config.DATA_DIR / "chunks.json"


def save_chunks(chunked: ChunkedBook, path: Path = CHUNKS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "parents": [asdict(p) for p in chunked.parents],
        "children": [asdict(c) for c in chunked.children],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_chunks(path: Path = CHUNKS_PATH) -> ChunkedBook:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/index.py` first to build the "
            "contextualized chunk store."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    parents = [ParentChunk(**p) for p in data["parents"]]
    children = [ChildChunk(**c) for c in data["children"]]
    return ChunkedBook(parents=parents, children=children)


def document_info(chunked: ChunkedBook) -> dict:
    """
    Derive document-level metadata from the loaded chunks, so the UI can show
    what's actually loaded (works for any book, no hard-coded title).

    The book title is stored on each chunk via its source; we recover the
    chapter list (number, title) and the page span from the parents.
    """
    # Unique chapters in order, keyed by chapter index.
    chapters: dict[int, dict] = {}
    max_page = 0
    for p in chunked.parents:
        max_page = max(max_page, p.end_page)
        if p.chapter_index not in chapters:
            chapters[p.chapter_index] = {
                "number": p.chapter_number,
                "title": p.chapter_title.title(),  # ALL-CAPS -> Title Case
            }
    ordered = [chapters[i] for i in sorted(chapters)]

    # Report the real page count from the source PDF, not the last indexed page
    # (trailing matter like the license page yields no chunks, so deriving the
    # count from chunks would undercount). Reading the PDF page count is cheap.
    n_pages = max_page + 1
    try:
        from pypdf import PdfReader
        n_pages = len(PdfReader(str(config.TEST_PDF)).pages)
    except Exception:
        pass

    return {
        "title": config.BOOK_TITLE,
        "chapters": ordered,
        "n_chapters": len(ordered),
        "n_pages": n_pages,
    }
