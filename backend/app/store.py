"""
Persistence for the contextualized chunks.

Contextualizing a book costs real API calls, so we run it once at upload time and
cache the result to disk as JSON (one file per document, under data/docs/<id>/).
The indexer and retriever load from here instead of re-contextualizing on every
run. Plain JSON (not a DB) keeps it inspectable — you can open the file and read
exactly what got indexed.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.chunker import ChunkedBook, ParentChunk, ChildChunk


def save_chunks(chunked: ChunkedBook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "parents": [asdict(p) for p in chunked.parents],
        "children": [asdict(c) for c in chunked.children],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_chunks(path: Path) -> ChunkedBook:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. This document's chunk store is missing or its "
            "indexing did not complete; re-upload the PDF to rebuild it."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    parents = [ParentChunk(**p) for p in data["parents"]]
    children = [ChildChunk(**c) for c in data["children"]]
    return ChunkedBook(parents=parents, children=children)


def document_info(chunked: ChunkedBook) -> dict:
    """
    Derive the chapter list (and a fallback page estimate) from the chunks.

    Only returns what is actually recoverable from the chunks: the ordered
    chapter list and a page count estimated from the last indexed page. The
    book's title and authoritative page count are NOT derivable from chunks —
    callers supply those (see library.document_info_for). This function is
    deliberately honest about that rather than substituting fixture values.
    """
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
    return {
        "chapters": ordered,
        "n_chapters": len(ordered),
        "n_pages": max_page + 1,  # 1-based estimate; caller overrides with the real count
    }
