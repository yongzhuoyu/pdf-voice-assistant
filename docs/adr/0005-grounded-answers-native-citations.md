# 0005 — Grounded answers with native citations

**Status:** Accepted
**Date:** 2026-06-25

## Context

Retrieval only matters if the final answer actually uses the retrieved passages
and nothing else. Two risks remain after good retrieval:

1. **Hallucination** — the model blends in outside knowledge or invents detail
   the passages do not support.
2. **Unverifiable grounding** — even a correct answer is hard to trust if the
   user cannot see *where* it came from in the book.

A third requirement is graceful refusal: when the book does not contain the
answer, the system should say so plainly rather than guess. The assignment
rewards this "the book doesn't cover that" behavior.

## Decision

Use Claude's **native citations**. Each retrieved parent passage is sent as a
`document` content block with `citations: {enabled: true}`. The model answers
using only those documents and returns its answer split into spans, each cited
span carrying which document it came from — which we map back to a chapter and
page for the UI's citation panel. This gives verifiable grounding for free,
without a separate citation-extraction step.

For scope detection, the system prompt instructs the model to begin its reply
with an explicit tag — `[ANSWERED]` or `[NOT_IN_BOOK]` — which is parsed
deterministically and then stripped before the answer is shown or spoken. A
question is flagged out-of-scope only when the model both tags it as such *and*
cites nothing, which avoids the contradictory case of a "not covered" banner
sitting above an answer that clearly discusses a partially-covered topic.

The model is **claude-opus-4-8** — the most capable model and the one with native
citation support.

## Consequences

**Positive**
- Every sentence in an answer is traceable to a specific passage, chapter, and
  page, with no bespoke citation logic to maintain.
- The deterministic scope tag makes out-of-scope handling reliable rather than a
  guess based on the prose.
- In the [evaluation](../TESTING.md), faithfulness scored 100% on in-scope
  questions and refusal fired correctly on both out-of-scope questions.

**Negative**
- Ties answer generation to a provider feature (Anthropic citations); a different
  LLM would need a different grounding mechanism.
- Citations are only as good as the retrieved passages — if retrieval misses, the
  model correctly refuses rather than inventing, which is the safe failure but
  still a miss.

## Related

Consumes passages from [the retriever](./0004-hybrid-search-rrf-rerank.md).
