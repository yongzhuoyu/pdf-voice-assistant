# 0001 — Python + FastAPI for the backend

**Status:** Accepted
**Date:** 2026-06-25

## Context

The application's hard part is the RAG pipeline: chunking, embeddings,
contextualization, hybrid search, reranking, and an answer-quality evaluation
harness. The mature, well-documented libraries for every one of those steps —
Chroma, `sentence-transformers` cross-encoders, `rank_bm25`, the Anthropic and
Deepgram SDKs, RAGAS-style evaluation — are Python-first. Several have no
equivalent in other ecosystems.

The developer's strength is web frameworks, not ML. A backend that reads like
ordinary request/response web code (rather than ML research) keeps the system
maintainable for that profile.

## Decision

Build the backend in **Python with FastAPI**.

FastAPI was chosen over Flask/Django because its routing, dependency model, and
async request handling map closely onto patterns the developer already knows from
JavaScript web frameworks (decorated route handlers, typed request bodies via
Pydantic, an Express-like feel), while giving first-class access to the Python
RAG ecosystem.

## Consequences

**Positive**
- Every retrieval component is a native, supported library rather than a port or
  a reimplementation.
- Pydantic request/response models give typed, self-validating endpoints.
- A single process (`uvicorn app.api:app`) runs the whole backend — trivial to
  start and to reason about.

**Negative**
- The frontend (React) and backend (Python) are two languages, so there is no
  shared type definition across the HTTP boundary; the API contract is kept in
  sync by hand and covered by end-to-end testing.
- Python's threading is used for background indexing rather than a dedicated job
  queue; acceptable at this scale, but it would need a real worker (e.g. Celery)
  to scale horizontally.
