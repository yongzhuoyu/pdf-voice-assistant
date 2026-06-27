# Architecture Decision Records

This directory records the significant technical decisions behind the project —
*what* was decided, the *context* that forced the decision, and the
*consequences* (good and bad) of going that way.

The format follows [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
each record is short, dated, and immutable. If a decision is later reversed, we
add a new record that supersedes the old one rather than editing history — the
point of an ADR is to preserve the reasoning as it was at the time.

| # | Decision | Status |
|---|---|---|
| [0001](./0001-backend-python-fastapi.md) | Python + FastAPI for the backend | Accepted |
| [0002](./0002-contextual-retrieval.md) | Contextual Retrieval over naive chunking | Accepted |
| [0003](./0003-parent-child-chunking.md) | Parent-child chunking | Accepted |
| [0004](./0004-hybrid-search-rrf-rerank.md) | Hybrid search + RRF + cross-encoder rerank | Accepted |
| [0005](./0005-grounded-answers-native-citations.md) | Grounded answers with native citations | Accepted |
| [0006](./0006-deepgram-voice-chroma-store.md) | Deepgram for voice, Chroma for the vector store | Accepted |

## Why these and not others

The assignment is graded on retrieval quality, so the cluster of retrieval
decisions ([0002](./0002-contextual-retrieval.md)–[0005](./0005-grounded-answers-native-citations.md))
is where the real reasoning lives. The infrastructure choices
([0001](./0001-backend-python-fastapi.md), [0006](./0006-deepgram-voice-chroma-store.md))
are recorded because they shaped everything else, but they were deliberately kept
boring: the goal was to spend complexity budget on retrieval, not on plumbing.
