# 0003 — Parent-child chunking

**Status:** Accepted
**Date:** 2026-06-25

## Context

Chunk size forces a trade-off that a single size cannot win:

- **Small chunks retrieve precisely.** A ~300-token chunk is "about" one thing,
  so its embedding is focused and a query vector matches it cleanly. But 300
  tokens is often too little context for the language model to actually answer
  the question well.
- **Large chunks give the model context** but retrieve poorly. A ~1200-token
  chunk spans several topics, so its embedding is a blurry average that matches
  any single query only weakly.

Pick one size and you sacrifice either retrieval precision or answer quality.

## Decision

Use **parent-child chunking** (the parent-document pattern). Split each chapter
into:

- **Child chunks (~300 tokens)** — these are embedded, contextualized, and
  searched. They exist to be *matched*.
- **Parent spans (~1200 tokens)** — larger sections that each child belongs to.
  When a child is retrieved, the language model is handed its parent span instead
  of the child itself.

Retrieval operates on children for precision; generation operates on parents for
context. Children carry a `parent_id`, and the retriever de-duplicates parents
(keeping the best child score) before expansion, so the model never receives the
same span twice.

## Consequences

**Positive**
- Gets precise matching *and* rich context, instead of compromising on one.
- Pairs naturally with the chapter-aware parser: parent spans align with real
  document sections, and citations resolve cleanly to a chapter and page.
- De-duplication at the parent level keeps the model's context window free of
  redundant passages.

**Negative**
- Two chunk granularities mean more bookkeeping (parent/child IDs, the expansion
  step) than a flat chunk list.
- Token counts are approximated (words × 1.3) rather than tokenizer-exact; chunk
  size is a tuning knob, not a value that needs token-perfect precision, so this
  keeps indexing fast at a small cost in boundary precision.

## Related

Children are the unit that [Contextual Retrieval](./0002-contextual-retrieval.md)
situates and [hybrid search](./0004-hybrid-search-rrf-rerank.md) ranks; parents
are what [the answerer](./0005-grounded-answers-native-citations.md) reads.
