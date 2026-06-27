# 0004 — Hybrid search + RRF + cross-encoder rerank

**Status:** Accepted
**Date:** 2026-06-25

## Context

Dense vector search alone has a known weakness: it matches meaning but blurs rare
exact tokens. A query for a specific proper noun ("Tillamook Rock", "Francis
Greenway") or an exact phrase can rank the right passage below paraphrase-similar
but wrong ones. Lexical (BM25) search has the opposite weakness: it nails exact
words but cannot match a paraphrase that shares no vocabulary with the source.

Neither single method is reliably good enough for "genuinely usable" answers.
Two further problems compound it: combining two ranked lists is awkward because
their score scales are incomparable, and the fast first-pass retrieval used by
either method is not the most accurate way to pick the *final* few passages.

## Decision

Run a three-stage retrieval pipeline (in `retriever.py`):

1. **Hybrid search.** Run dense (Chroma) and BM25 in parallel, each returning its
   own ranked candidate list.
2. **Reciprocal Rank Fusion (RRF).** Merge the two lists by *rank*, not score:
   `score(d) = Σ 1 / (k + rank(d))` over both lists, with `k = 60` (the constant
   from the original RRF paper). This sidesteps the incomparable-scales problem
   entirely — a passage ranked highly by either method rises, and one ranked
   highly by both wins.
3. **Cross-encoder reranking.** Take the fused shortlist and re-score it with a
   cross-encoder (`ms-marco-MiniLM-L-6-v2`), which reads each (query, passage)
   pair *together* rather than embedding them separately. This is slower, so it
   only runs on the shortlist, but it is far more accurate for the final pick.

The reranked children are then expanded to their parent spans (see
[ADR-0003](./0003-parent-child-chunking.md)) and the top few are returned.

## Consequences

**Positive**
- Covers both failure modes: paraphrase (dense) and exact terms (lexical).
- RRF needs no score normalization or tuning beyond the standard `k`, so fusion
  is robust and parameter-light.
- The cross-encoder measurably improves the final ordering; in the
  [evaluation](../TESTING.md), the chapter holding the answer was ranked first in
  every in-scope question.

**Negative**
- The cross-encoder is a few-hundred-MB model that must be loaded into memory; it
  is kept as a process-wide singleton and warmed at startup so it does not stall
  the first query.
- More moving parts than a single vector search, and BM25 is held in memory, so
  very large corpora would need a more scalable lexical index.

## Related

Consumes the [contextualized](./0002-contextual-retrieval.md),
[parent-child](./0003-parent-child-chunking.md) index; hands results to
[the answerer](./0005-grounded-answers-native-citations.md).
