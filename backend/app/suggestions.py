"""
Per-book starter questions.

The UI shows a few "Try asking" examples to nudge the user. Hard-coding them
ties the UI to one book, so we generate them from the actual content: one cheap
Claude call at index time reads a sample of the book and proposes good,
specific, answerable questions. Stored with the document and served via
/document so the examples match whatever book is loaded.
"""

from __future__ import annotations

import json

import anthropic

from app import config
from app.chunker import ChunkedBook


_SYSTEM = (
    "You write sample questions a reader might ask about a book, to seed a "
    "question-answering interface. Given excerpts from the book, output 4 short, "
    "specific questions that are clearly answerable from this book's content. "
    "Vary them across different parts of the book. Each under 12 words. "
    "Respond ONLY with a JSON array of 4 strings, nothing else."
)

# Generic fallback if generation fails — still book-agnostic and useful.
_FALLBACK = [
    "What is this book about?",
    "Summarize the opening.",
    "Who or what does it focus on?",
    "What happens first?",
]


def generate_starter_questions(book_title: str, chunked: ChunkedBook) -> list[str]:
    """
    Return 4 starter questions tailored to the book. Falls back to generic
    prompts on any error so indexing never fails because of this nicety.
    """
    if not config.ANTHROPIC_API_KEY:
        return _FALLBACK

    # Sample a handful of parent chunks spread across the book so the model sees
    # varied content without us sending the whole text.
    parents = chunked.parents
    if not parents:
        return _FALLBACK
    step = max(1, len(parents) // 6)
    sample = parents[::step][:6]
    excerpts = "\n\n---\n\n".join(p.text[:600] for p in sample)

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.CONTEXT_MODEL,   # cheap model; this is a one-off per book
            max_tokens=300,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Book: {book_title}\n\nExcerpts:\n{excerpts}",
            }],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        # The model may wrap the array in prose or a code fence; extract the array.
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            questions = json.loads(text[start:end + 1])
            cleaned = [str(q).strip() for q in questions if str(q).strip()]
            if len(cleaned) >= 3:
                return cleaned[:4]
    except Exception:
        pass
    return _FALLBACK
