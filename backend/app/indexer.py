"""
Indexer — builds the two search indexes the hybrid retriever fuses.

Why two indexes, not one:
  - DENSE (vector) search matches on *meaning*. "Did the king confess?" finds a
    passage about admitting to an affair even with no shared words. Great for
    paraphrase, weak on exact names/IDs.
  - BM25 (lexical) search matches on *words*. It nails rare proper nouns and
    exact phrases ("Irene Adler", "Boscombe Valley") that a dense model may
    blur. Weak on paraphrase.

They fail in opposite ways, so fusing them (done in retriever.py) beats either
alone. Both index the CONTEXTUALIZED text (situating sentence + chunk) so the
Contextual Retrieval benefit applies to both halves.

Chroma runs locally and persists to disk (no server). For embeddings we use
Chroma's built-in default model so Day 1 needs no embedding API key — the only
API cost is the one-time contextualization.
"""

from __future__ import annotations

import chromadb
from rank_bm25 import BM25Okapi

from app import config
from app.chunker import ChunkedBook, ChildChunk
from app.contextualizer import embedding_text

_DEFAULT_COLLECTION = "sherlock_children"


def _collection_name(document_id: str | None) -> str:
    """Per-document Chroma collection. The original single book keeps its name."""
    return _DEFAULT_COLLECTION if document_id is None else f"doc_{document_id}"


def _tokenize(text: str) -> list[str]:
    """Simple lowercase word tokenizer for BM25."""
    import re
    return re.findall(r"[a-z0-9']+", text.lower())


class HybridIndex:
    """Holds the dense (Chroma) collection and the in-memory BM25 index."""

    def __init__(self, children: list[ChildChunk], document_id: str | None = None):
        self.children = children
        self.document_id = document_id
        self._collection_name = _collection_name(document_id)
        self.by_id = {c.id: c for c in children}
        # BM25 over the contextualized text, in child order.
        self._bm25_ids = [c.id for c in children]
        self._bm25 = BM25Okapi([_tokenize(embedding_text(c)) for c in children])
        # Dense collection handle set in build()/load().
        self._collection = None

    # --- dense (Chroma) ---
    def _client(self):
        return chromadb.PersistentClient(path=str(config.CHROMA_DIR))

    def build_dense(self) -> None:
        client = self._client()
        # Fresh collection each build so re-indexing is idempotent.
        try:
            client.delete_collection(self._collection_name)
        except Exception:
            pass
        coll = client.create_collection(self._collection_name, metadata={"hnsw:space": "cosine"})
        coll.add(
            ids=[c.id for c in self.children],
            documents=[embedding_text(c) for c in self.children],
            metadatas=[{
                "parent_id": c.parent_id,
                "chapter_index": c.chapter_index,
                "chapter_number": c.chapter_number,
                "chapter_title": c.chapter_title,
                "page": c.page,
            } for c in self.children],
        )
        self._collection = coll

    def load_dense(self) -> None:
        self._collection = self._client().get_collection(self._collection_name)

    # --- queries (used by retriever.py) ---
    def dense_search(self, query: str, k: int) -> list[tuple[str, float]]:
        res = self._collection.query(query_texts=[query], n_results=k)
        ids = res["ids"][0]
        dists = res["distances"][0]
        # Return (id, similarity) — cosine distance → similarity.
        return [(i, 1.0 - d) for i, d in zip(ids, dists)]

    def bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._bm25_ids, scores), key=lambda x: x[1], reverse=True)
        return ranked[:k]


def build_index(chunked: ChunkedBook, document_id: str | None = None) -> HybridIndex:
    idx = HybridIndex(chunked.children, document_id=document_id)
    idx.build_dense()
    return idx


def load_index(chunked: ChunkedBook, document_id: str | None = None) -> HybridIndex:
    idx = HybridIndex(chunked.children, document_id=document_id)
    idx.load_dense()
    return idx
