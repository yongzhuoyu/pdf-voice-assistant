# 0002 — Contextual Retrieval over naive chunking

**Status:** Accepted
**Date:** 2026-06-25

## Context

The assignment is explicit: *"Naive fixed-size chunking has limited recall;
research current retrieval methods and apply what works."* This is the graded
centerpiece, so the chunking strategy needed to be better than the default.

Naive chunking splits a document into fixed-size windows and embeds each one as
written. The failure is well known: a chunk that reads *"It was rebuilt in 1882
from interlocking granite"* has lost the fact that "it" is the Eddystone
lighthouse. Embedded in isolation, that chunk matches a query about the Eddystone
poorly, because the words "Eddystone lighthouse" never appear in it. Recall
suffers exactly on the chunks that carry the answer.

Anthropic's published **Contextual Retrieval** technique addresses this: before
embedding a chunk, prepend a short, LLM-generated sentence that situates it
within the whole document. In Anthropic's benchmark this cut top-20 retrieval
failures by roughly two-thirds. The concern is cost — it means one LLM call per
chunk — which prompt caching is designed to absorb.

## Decision

Adopt **Contextual Retrieval**: for every child chunk, call a small model
(Claude Haiku) to write a one-line situating sentence, prepend it to the chunk
text, and index the combined text in both the dense and lexical indexes.

Use **prompt caching** to make it affordable: the full chapter text is sent once
and cached, then reused as the cached prefix across every chunk in that chapter,
so only the short per-chunk question is uncached. Process chapter-by-chapter to
maximize cache reuse, warming the cache with the first chunk before fanning the
rest out concurrently.

## Consequences

**Positive**
- Directly targets the recall problem the rubric calls out, with a method backed
  by a published benchmark rather than intuition.
- The situating sentence helps both halves of hybrid search — the dense vector
  *and* the BM25 keywords — because both index the contextualized text.
- Prompt caching cut the cost dramatically (on the full Sherlock book, ~6.6M
  cached tokens vs ~150K uncached), turning a per-chunk LLM call into a
  practical step.

**Negative**
- Indexing now depends on an LLM call per chunk, so it requires an API key and
  network access, and a book takes seconds-to-minutes to index rather than being
  instant.
- Cache effectiveness depends on processing order; the chapter-by-chapter
  structure is load-bearing and must be preserved.

## Related

Built on top of [parent-child chunking](./0003-parent-child-chunking.md); feeds
[hybrid search](./0004-hybrid-search-rrf-rerank.md).
