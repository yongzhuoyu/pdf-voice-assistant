# 0006 — Deepgram for voice, Chroma for the vector store

**Status:** Accepted
**Date:** 2026-06-25

## Context

Two infrastructure choices needed making, and the guiding principle for both was
to **spend the project's complexity budget on retrieval, not on plumbing**. The
assignment explicitly allows any cloud ASR/TTS/LLM service and free trial tiers,
and says self-hosting models is not required.

**Voice (ASR + TTS).** The pipeline needs speech-to-text on the way in and
text-to-speech on the way out. Options ranged from browser-native APIs (zero
cost, inconsistent quality and browser support) to self-hosted models (accurate,
but operationally heavy) to managed cloud APIs.

**Vector store.** The dense index needs somewhere to live. Options ranged from a
hosted vector database (Pinecone, Weaviate) to a local embedded store.

## Decision

**Deepgram** for both ASR (Nova) and TTS (Aura), over its REST API. One provider
covers both directions of the voice pipeline, so there is a single key and a
single integration. The REST interface feels like any other web API, which fits
the developer's strengths, and the free credit covers the project comfortably.
Text-to-speech is placed behind a small pluggable interface so the voice provider
can be swapped (e.g. to ElevenLabs for a final demo voice) without touching the
pipeline.

**Chroma** for the vector store, running locally and persisting to disk with no
separate server. It uses a built-in default embedding model, so the dense index
needs no additional embedding API key — the only indexing API cost is the
one-time contextualization.

## Consequences

**Positive**
- Voice is one provider, one key, one SDK pattern — minimal integration surface.
- The pluggable synthesizer keeps the voice choice from leaking into the rest of
  the system.
- Chroma needs no infrastructure: the whole backend is still a single process
  with a local data directory, so the project runs from a clone with two API keys
  and nothing to provision.
- Per-document Chroma collections (`doc_<id>`) give clean multi-book isolation and
  deletion.

**Negative**
- Voice quality and latency depend on an external service and network round-trips.
- A local, in-process Chroma store does not scale to many concurrent users or
  very large corpora; a hosted vector DB would be the next step if it needed to.
- Two external providers (Anthropic + Deepgram) means two keys to manage and two
  potential points of failure in the request path.
