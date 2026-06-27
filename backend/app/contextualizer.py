"""
Contextual Retrieval — the graded centerpiece.

The problem with plain chunking: a 300-token chunk ripped out of a book loses
its context. "He denied everything" — who is "he"? Which case? Embeddings and
BM25 can't match a query like "did the king admit to the affair" against a chunk
that never names the king. Anthropic's Contextual Retrieval fixes this by asking
an LLM to write a short situating sentence for each chunk, which we prepend
before embedding/indexing. In their benchmark this cut top-20 retrieval failures
by ~49% (and ~67% combined with reranking).

Cost control via prompt caching: naively, situating 544 chunks means sending the
chapter text 544 times. Instead we send each chapter's full text ONCE as a cached
prefix (`cache_control: ephemeral`), then vary only the small per-chunk question.
Cache writes cost ~1.25x but reads cost ~0.1x, so every chunk after the first in
a chapter is cheap. We process chunks grouped by chapter to keep the cache warm.

Model: claude-haiku-4-5 — situating a chunk is a simple task; Haiku is cheap and
fast, and we reserve Opus 4.8 for the final grounded answer.
"""

from __future__ import annotations

import anthropic

from app import config
from app.chunker import ChunkedBook, ChildChunk
from app.parser import ParsedBook


# The situating instruction. The cached prefix carries the whole chapter; this
# system instruction is stable too, so it caches alongside.
_SYSTEM = (
    "You situate a short excerpt within its chapter so it can be retrieved on "
    "its own. Given the full chapter and one excerpt from it, write a single "
    "concise sentence (under 30 words) that states who and what the excerpt is "
    "about — naming the people, place, and situation a reader would need to find "
    "this passage. Do not summarize the whole chapter. Output only the sentence, "
    "no preamble."
)


def _context_for_chunk(
    client: anthropic.Anthropic,
    chapter_title: str,
    chapter_text: str,
    chunk_text: str,
) -> str:
    """
    One contextualization call. The chapter text is the cacheable prefix; only
    the excerpt (last block) varies per chunk, so repeated calls within the same
    chapter read the cache instead of re-billing the chapter.
    """
    resp = client.messages.create(
        model=config.CONTEXT_MODEL,
        max_tokens=80,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Chapter: {chapter_title}\n\n<chapter>\n{chapter_text}\n</chapter>",
                    # Cache the chapter: written once, read for every chunk in it.
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"Excerpt to situate:\n<excerpt>\n{chunk_text}\n</excerpt>",
                },
            ],
        }],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    usage = resp.usage
    return text.strip(), usage


def contextualize(
    book: ParsedBook,
    chunked: ChunkedBook,
    *,
    progress: bool = True,
    on_chunk=None,   # optional callback(done:int, total:int) for progress UIs
) -> ChunkedBook:
    """
    Fill in `child.context` for every child chunk, in place. Returns the same
    ChunkedBook for convenience.

    Processes chapter-by-chapter so each chapter's cached prefix is reused across
    all its chunks. Prints running cache-hit stats so the savings are visible
    (and so we can prove prompt caching is actually working).
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    client = anthropic.Anthropic(api_key=config.require_anthropic_key())
    chapter_text = {c.index: c.text for c in book.chapters}
    chapter_title = {c.index: c.title for c in book.chapters}

    # Group children by chapter. The prompt cache is keyed on the chapter prefix,
    # so chunks in the same chapter share a cache entry.
    by_chapter: dict[int, list[ChildChunk]] = {}
    for c in chunked.children:
        by_chapter.setdefault(c.chapter_index, []).append(c)

    total = len(chunked.children)
    counters = {"done": 0, "cache_read": 0, "cache_write": 0, "uncached": 0}
    lock = threading.Lock()

    def run_one(child: ChildChunk):
        ctx, usage = _context_for_chunk(
            client, chapter_title[child.chapter_index],
            chapter_text[child.chapter_index], child.text
        )
        child.context = ctx
        with lock:
            counters["done"] += 1
            counters["cache_read"] += usage.cache_read_input_tokens or 0
            counters["cache_write"] += usage.cache_creation_input_tokens or 0
            counters["uncached"] += usage.input_tokens or 0
            done = counters["done"]
        if on_chunk:
            on_chunk(done, total)
        if progress and (done % 25 == 0 or done == total):
            print(f"  contextualized {done}/{total}  "
                  f"(cache_read={counters['cache_read']} "
                  f"cache_write={counters['cache_write']} "
                  f"uncached={counters['uncached']})")

    # Per chapter: run the FIRST chunk alone to WRITE the chapter into the cache,
    # then fan the rest out concurrently so they all READ that warm cache. Firing
    # a chapter's chunks all at once would make them miss the not-yet-written
    # cache and re-bill the chapter every time.
    with ThreadPoolExecutor(max_workers=config.CONTEXT_CONCURRENCY) as pool:
        for ch_idx in sorted(by_chapter):
            kids = by_chapter[ch_idx]
            if not kids:
                continue
            run_one(kids[0])              # warm the cache (synchronous)
            if len(kids) > 1:
                list(pool.map(run_one, kids[1:]))  # parallel reads

    if progress:
        print(f"  done. cache reads saved ~{counters['cache_read']} input tokens "
              f"from full price (~90% cheaper on those).")
    return chunked


def embedding_text(child: ChildChunk) -> str:
    """
    The text we actually index: the situating context prepended to the chunk.
    Used by both the dense embedder and BM25 so search matches the contextualized
    form, while the raw `child.text` is what we show/cite.
    """
    if child.context:
        return f"{child.context}\n\n{child.text}"
    return child.text
