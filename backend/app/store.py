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
