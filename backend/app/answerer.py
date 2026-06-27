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


# The model begins every reply with one of these exact tags so we can detect
# scope deterministically instead of guessing from the prose. We strip the tag
# before showing/speaking the answer.
_IN_SCOPE_TAG = "[ANSWERED]"
_OUT_OF_SCOPE_TAG = "[NOT_IN_BOOK]"

_SYSTEM = (
    "You answer questions about a book using ONLY the provided source passages.\n"
    "\n"
    "Begin your reply with a scope tag on its own, before anything else:\n"
    f"  - {_IN_SCOPE_TAG} if the passages actually contain the answer.\n"
    f"  - {_OUT_OF_SCOPE_TAG} if they do not — even if the topic is mentioned in "
    "passing but the specific answer is absent.\n"
    "\n"
    "After the tag, write the answer. Ground every claim in the sources and let "
    "the citation system attribute it. If out of scope, say plainly that the book "
    "does not cover it — never use outside knowledge or guess. Keep answers "
    "concise and direct; this answer will be read aloud, so avoid markdown, "
    "lists, and parenthetical citations in the prose."
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

    # Strip the model's scope tag from the spoken text.
    tagged_out_of_scope = False
    if answer_text.startswith(_OUT_OF_SCOPE_TAG):
        tagged_out_of_scope = True
        answer_text = answer_text[len(_OUT_OF_SCOPE_TAG):].lstrip()
    elif answer_text.startswith(_IN_SCOPE_TAG):
        answer_text = answer_text[len(_IN_SCOPE_TAG):].lstrip()

    # Only flag out-of-scope when the question is FULLY unanswerable from the
    # book — i.e. the model cited nothing. If it grounded its answer in real
    # passages (citations exist), it's in-scope even if it noted a gap ("the
    # book describes X but doesn't say Y"). This avoids the contradictory
    # "Not covered" banner sitting above an answer that clearly discusses the
    # topic, which happens when a book only partially covers a question.
    out_of_scope = tagged_out_of_scope and not citations

    return Answer(text=answer_text, citations=citations, out_of_scope=out_of_scope)
