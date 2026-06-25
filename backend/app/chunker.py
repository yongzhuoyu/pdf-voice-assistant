"""
Parent-child chunking.

The core idea (from Anthropic's Contextual Retrieval work and the parent-document
pattern): there's a tension between retrieval precision and answer context.

  - SMALL chunks retrieve precisely. A 300-token chunk is "about" one thing, so a
    query vector matches it cleanly. But 300 tokens is often too little context
    for the LLM to answer well.
  - LARGE chunks give the LLM context, but retrieve poorly — a 1200-token chunk
    covers several topics, so its embedding is a blurry average and matches weakly.

Parent-child resolves this: we index the SMALL children for matching, but when a
child is retrieved we hand the LLM its LARGER parent span. Precise retrieval,
rich context.

Token counting: we approximate tokens as words * 1.3 (a stable rule of thumb for
English prose) instead of calling the tokenizer per chunk. Chunk size is a tuning
knob, not a value that needs token-perfect precision, so the approximation keeps
indexing fast and free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import config
from app.parser import Chapter, ParsedBook


# Roughly tokens-per-word for English. Used only to size chunks, not to bill.
_TOKENS_PER_WORD = 1.3


@dataclass
class ParentChunk:
    """A larger span (≈section) handed to the LLM for context."""

    id: str                 # e.g. "ch07-p02"
    chapter_index: int
    chapter_number: str
    chapter_title: str
    start_page: int
    end_page: int
    text: str


@dataclass
class ChildChunk:
    """A small span indexed for precise retrieval; points back to its parent."""

    id: str                 # e.g. "ch07-p02-c03"
    parent_id: str
    chapter_index: int
    chapter_number: str
    chapter_title: str
    page: int               # best-effort page this chunk's text sits on (citation)
    text: str
    # Filled later by the contextualizer (Claude-generated one-line context).
    context: str = ""


@dataclass
class ChunkedBook:
    parents: list[ParentChunk]
    children: list[ChildChunk]


def _approx_tokens(text: str) -> int:
    return int(len(text.split()) * _TOKENS_PER_WORD)


def _split_sentences(text: str) -> list[str]:
    """
    Lightweight sentence splitter. We split on sentence-ending punctuation
    followed by whitespace. Not perfect (abbreviations etc.), but chunk
    boundaries only need to land on roughly-sentence edges so we never cut a
    sentence in half — which would hurt both embedding and readability.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Keep the delimiter with the sentence it ends.
    parts = re.split(r"(?<=[.!?”\"])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _page_for_offset(chapter: Chapter, char_offset: int) -> int:
    """
    Map a character offset within a chapter's concatenated text back to the PDF
    page it falls on, so a child chunk can cite the right page. The chapter
    stores per-page text in order; we walk cumulative lengths.
    """
    cum = 0
    for page, ptext in chapter.page_texts:
        # +1 for the "\n" join between pages in Chapter.text.
        cum += len(ptext) + 1
        if char_offset < cum:
            return page
    return chapter.page_texts[-1][0] if chapter.page_texts else chapter.start_page


def _pack(sentences: list[str], max_tokens: int) -> list[tuple[str, int]]:
    """
    Greedily pack sentences into chunks up to max_tokens. Returns a list of
    (chunk_text, start_sentence_index) so callers can recover position.
    """
    chunks: list[tuple[str, int]] = []
    buf: list[str] = []
    buf_tokens = 0
    start_idx = 0
    for i, sent in enumerate(sentences):
        st = _approx_tokens(sent)
        if buf and buf_tokens + st > max_tokens:
            chunks.append((" ".join(buf), start_idx))
            buf, buf_tokens, start_idx = [], 0, i
        buf.append(sent)
        buf_tokens += st
    if buf:
        chunks.append((" ".join(buf), start_idx))
    return chunks


def chunk_book(book: ParsedBook) -> ChunkedBook:
    """
    Turn a parsed book into parent and child chunks.

    For each chapter:
      1. Split into parent chunks (~PARENT_CHUNK_TOKENS) along sentence edges.
      2. Split each parent into child chunks (~CHILD_CHUNK_TOKENS).
    Each child records the page it sits on (for citation) and its parent id.
    """
    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []

    for ch in book.chapters:
        sentences = _split_sentences(ch.text)
        # Track character offset as we consume sentences, to map to pages.
        # Rebuild offsets by locating each parent's first sentence in ch.text.
        parent_spans = _pack(sentences, config.PARENT_CHUNK_TOKENS)

        for p_i, (p_text, _p_start) in enumerate(parent_spans, start=1):
            parent_id = f"ch{ch.index:02d}-p{p_i:02d}"
            # Page range for the parent: locate its text span in the chapter.
            p_offset = ch.text.find(p_text[:80]) if p_text else -1
            p_start_page = _page_for_offset(ch, max(p_offset, 0))
            p_end_page = _page_for_offset(ch, max(p_offset, 0) + len(p_text))
            parents.append(ParentChunk(
                id=parent_id, chapter_index=ch.index, chapter_number=ch.number,
                chapter_title=ch.title, start_page=p_start_page,
                end_page=p_end_page, text=p_text,
            ))

            # Children within this parent.
            child_sents = _split_sentences(p_text)
            child_spans = _pack(child_sents, config.CHILD_CHUNK_TOKENS)
            for c_i, (c_text, _c_start) in enumerate(child_spans, start=1):
                c_offset = ch.text.find(c_text[:60])
                page = _page_for_offset(ch, c_offset if c_offset >= 0 else max(p_offset, 0))
                children.append(ChildChunk(
                    id=f"{parent_id}-c{c_i:02d}", parent_id=parent_id,
                    chapter_index=ch.index, chapter_number=ch.number,
                    chapter_title=ch.title, page=page, text=c_text,
                ))

    return ChunkedBook(parents=parents, children=children)
