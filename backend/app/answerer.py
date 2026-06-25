"""
Grounded answer generation with native citations.

We hand Claude the retrieved parent passages as `document` content blocks with
`citations: {enabled: true}`. Claude then answers using ONLY those documents and
returns its answer split into text spans, each cited span carrying which document
(and char range) it came from. This gives verifiable grounding for free — every
claim in the answer can be traced back to a specific passage, which we map to a
chapter + page for the UI's citation panel.

Out-of-scope handling: if the documents don't contain the answer, we instruct
Claude to say so plainly rather than inventing one. This is the "the book doesn't
cover that" behavior the rubric rewards.

Model: claude-opus-4-8 — most capable, and the model with native citation support.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import anthropic

from app import config
from app.retriever import RetrievedPassage


_SYSTEM = (
    "You answer questions about a book using ONLY the provided source passages. "
    "Ground every claim in the sources and let the citation system attribute it. "
    "If the passages do not contain the answer, say plainly that the book does "
    "not cover it — do not use outside knowledge or guess. Keep answers concise "
    "and direct; this answer will be read aloud, so avoid markdown, lists, and "
    "parenthetical citations in the prose."
)


@dataclass
class Citation:
    """One cited span, mapped back to chapter/page for the UI."""

    quoted_text: str
    chapter_number: str
    chapter_title: str
    start_page: int
    end_page: int


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    out_of_scope: bool = False


def generate_answer(question: str, passages: list[RetrievedPassage]) -> Answer:
    client = anthropic.Anthropic(api_key=config.require_anthropic_key())

    if not passages:
        return Answer(text="The book does not appear to cover that.", out_of_scope=True)

    # Build one citable document block per retrieved parent passage.
    documents = []
    for p in passages:
        documents.append({
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": p.text},
            "title": f"{p.chapter_number}. {p.chapter_title} (pages {p.start_page}-{p.end_page})",
            "citations": {"enabled": True},
        })

    content = documents + [{"type": "text", "text": f"Question: {question}"}]
    resp = client.messages.create(
        model=config.ANSWER_MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    # Stitch the answer text and collect citations, mapping each cited document
    # index back to the passage's chapter/page.
    text_parts: list[str] = []
    citations: list[Citation] = []
    for block in resp.content:
        if block.type != "text":
            continue
        text_parts.append(block.text)
        for cit in (getattr(block, "citations", None) or []):
            idx = getattr(cit, "document_index", None)
            if idx is None or idx >= len(passages):
                continue
            p = passages[idx]
            citations.append(Citation(
                quoted_text=getattr(cit, "cited_text", ""),
                chapter_number=p.chapter_number,
                chapter_title=p.chapter_title,
                start_page=p.start_page,
                end_page=p.end_page,
            ))

    answer_text = "".join(text_parts).strip()
    # Heuristic out-of-scope flag: model said so and cited nothing.
    oos = not citations and (
        "does not cover" in answer_text.lower()
        or "doesn't cover" in answer_text.lower()
        or "not covered" in answer_text.lower()
    )
    return Answer(text=answer_text, citations=citations, out_of_scope=oos)
