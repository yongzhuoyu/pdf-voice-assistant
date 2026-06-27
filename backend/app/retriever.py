"""
Retriever — turns a question into the handful of passages the LLM will answer
from. This is the last and most decisive stage of retrieval quality.

Pipeline (each step is a known, measurable improvement over naive top-k):

  1. Hybrid search: run dense (semantic) and BM25 (lexical) in parallel. Each
     returns its own ranked candidate list.
  2. Reciprocal Rank Fusion (RRF): merge the two lists by RANK, not score, so we
     don't have to reconcile incomparable score scales. A chunk ranked highly by
     either method floats up; a chunk ranked highly by BOTH wins.
  3. Rerank: a cross-encoder reads (query, chunk) pairs together and scores true
     relevance — far more accurate than the bi-encoder vectors used for fast
     first-pass retrieval. We rerank the fused candidates and keep the top few.
  4. Parent expansion: we matched on small child chunks for precision, but hand
     the LLM each child's larger PARENT span so it has enough context to answer.

RRF formula: score(d) = sum over lists of 1 / (k + rank(d)), k=60 (the standard
constant from the original RRF paper). Rank is 1-based.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentence_transformers import CrossEncoder

from app import config
from app.chunker import ChunkedBook, ParentChunk
from app.indexer import HybridIndex


@dataclass
class RetrievedPassage:
    """A parent span selected to answer from, with citation metadata."""

    parent_id: str
    chapter_number: str
    chapter_title: str
    start_page: int
    end_page: int
    text: str
    rerank_score: float


def _rrf_fuse(
    dense: list[tuple[str, float]],
    bm25: list[tuple[str, float]],
    k: int = config.RRF_K,
) -> list[str]:
    """Fuse two ranked id-lists by Reciprocal Rank Fusion; return ids best-first."""
    scores: dict[str, float] = {}
    for ranked in (dense, bm25):
        for rank, (cid, _score) in enumerate(ranked, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


# The cross-encoder reranker is loaded ONCE and shared across all books. It's a
# few hundred MB and stateless, so one instance serves every retriever. Loading
# it per-book (in __init__) made the first query on each book block for seconds
# while weights loaded — which looked like the app hanging after an upload.
_RERANKER: CrossEncoder | None = None
_RERANKER_LOCK = __import__("threading").Lock()


def get_reranker() -> CrossEncoder:
    global _RERANKER
    if _RERANKER is None:
        with _RERANKER_LOCK:
            if _RERANKER is None:
                _RERANKER = CrossEncoder(config.RERANK_MODEL)
    return _RERANKER


class Retriever:
    def __init__(self, index: HybridIndex, chunked: ChunkedBook):
        self.index = index
        self.chunked = chunked
        self.parents: dict[str, ParentChunk] = {p.id: p for p in chunked.parents}
        self._reranker = get_reranker()  # shared singleton, loaded once

    def retrieve(self, query: str, *, top_k: int = config.FINAL_TOP_K) -> list[RetrievedPassage]:
        # 1. Hybrid first-pass.
        dense = self.index.dense_search(query, config.DENSE_TOP_K)
        bm25 = self.index.bm25_search(query, config.BM25_TOP_K)

        # 2. Fuse by rank.
        fused_ids = _rrf_fuse(dense, bm25)
        if not fused_ids:
            return []

        # 3. Rerank the fused child candidates with the cross-encoder.
        cand = fused_ids[: max(config.DENSE_TOP_K, config.BM25_TOP_K)]
        pairs = [(query, self.index.by_id[cid].text) for cid in cand]
        scores = self._reranker.predict(pairs)
        reranked = sorted(zip(cand, scores), key=lambda x: x[1], reverse=True)

        # 4. Expand children -> parents, dedup parents (keep best child score),
        #    and return the top_k parent spans.
        seen: dict[str, float] = {}
        order: list[str] = []
        for cid, score in reranked:
            pid = self.index.by_id[cid].parent_id
            if pid not in seen:
                seen[pid] = float(score)
                order.append(pid)
            else:
                seen[pid] = max(seen[pid], float(score))
            if len(order) >= top_k:
                break

        out: list[RetrievedPassage] = []
        for pid in order[:top_k]:
            p = self.parents[pid]
            out.append(RetrievedPassage(
                parent_id=p.id, chapter_number=p.chapter_number,
                chapter_title=p.chapter_title, start_page=p.start_page,
                end_page=p.end_page, text=p.text, rerank_score=seen[pid],
            ))
        return out
