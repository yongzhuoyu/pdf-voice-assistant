"""
Chapter-aware PDF parser.

Why this is the foundation of retrieval quality: generic RAG treats a PDF as one
flat blob of text. We instead recover the book's real structure — which chapter
each passage belongs to, and what page it's on — so we can (a) feed the LLM the
right *parent* span for context and (b) cite chapter + page in the answer.

Two judgment calls drive the design (documented in CLAUDE.md):

  1. Chapter headings line-wrap on extraction. "VII. THE ADVENTURE OF THE BLUE"
     spills "CARBUNCLE" onto the next line. We reassemble before matching.

  2. The book reuses "I. II. III." for BOTH chapter numbers AND internal
     scene-break markers. A bare "I." with no title is a scene break, not a new
     chapter. So we do NOT trust a roman-numeral regex alone — we cross-reference
     the reassembled heading against the KNOWN canonical title list. A scene
     break can't accidentally match a real title, so this is robust.

The known-title-list trick is what a generic enterprise KB (e.g. Bedrock
Knowledge Bases) can't do — it can't assume it knows the book's table of
contents. We can, and we exploit it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader


# The canonical table of contents for the test book. Detection cross-references
# against this so scene-break "I."s and OCR noise can't be mistaken for chapters.
# (number, title) — titles are uppercase as they render in the headings.
KNOWN_CHAPTERS: list[tuple[str, str]] = [
    ("I", "A SCANDAL IN BOHEMIA"),
    ("II", "THE RED-HEADED LEAGUE"),
    ("III", "A CASE OF IDENTITY"),
    ("IV", "THE BOSCOMBE VALLEY MYSTERY"),
    ("V", "THE FIVE ORANGE PIPS"),
    ("VI", "THE MAN WITH THE TWISTED LIP"),
    ("VII", "THE ADVENTURE OF THE BLUE CARBUNCLE"),
    ("VIII", "THE ADVENTURE OF THE SPECKLED BAND"),
    ("IX", "THE ADVENTURE OF THE ENGINEER'S THUMB"),
    ("X", "THE ADVENTURE OF THE NOBLE BACHELOR"),
    ("XI", "THE ADVENTURE OF THE BERYL CORONET"),
    ("XII", "THE ADVENTURE OF THE COPPER BEECHES"),
]

# A line that *might* start a heading: a roman numeral, a dot, then SOME caps.
# This is only a cheap pre-filter — the real decision is the title-list match.
_HEADING_START = re.compile(r"^([IVXL]+)\.\s+([A-Z].*)$")


@dataclass
class Chapter:
    """One detected chapter and the text/pages it spans."""

    number: str            # roman numeral, e.g. "VII"
    index: int             # 1-based order in the book
    title: str             # canonical title, e.g. "THE ADVENTURE OF THE BLUE CARBUNCLE"
    start_page: int        # 0-based page where the heading appears
    end_page: int = -1     # 0-based last page of the chapter (set after all found)
    text: str = ""         # full chapter body text (filled in second pass)
    # Per-page text so a chunk's page can be recovered for citation.
    page_texts: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class ParsedBook:
    title: str
    chapters: list[Chapter]
    n_pages: int


def _normalize(s: str) -> str:
    """
    Canonicalize for comparison: collapse whitespace, normalize unicode
    punctuation (curly vs straight apostrophe), uppercase. The source uses a
    curly apostrophe in "ENGINEER'S"; extraction may differ, so we fold both.
    """
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'")  # curly → straight
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


# Pre-normalize the known titles once, keyed by (number, normalized-title).
_KNOWN_NORM = {(_normalize(n), _normalize(t)) for n, t in KNOWN_CHAPTERS}
_KNOWN_BY_NUM = {_normalize(n): _normalize(t) for n, t in KNOWN_CHAPTERS}


def _match_heading(lines: list[str]) -> tuple[str, str] | None:
    """
    Given the first few non-empty lines of a page, decide whether they form a
    real chapter heading. Returns (number, canonical_title) or None.

    Handles line-wrapping by greedily appending up to two following lines to the
    candidate title and checking each against the known list. This is what lets
    "VII. THE ADVENTURE OF THE BLUE" + "CARBUNCLE" resolve correctly, while a
    bare "I." (scene break) matches nothing and is rejected.
    """
    if not lines:
        return None
    m = _HEADING_START.match(lines[0].strip())
    if not m:
        return None
    num = _normalize(m.group(1))
    if num not in _KNOWN_BY_NUM:
        return None
    expected = _KNOWN_BY_NUM[num]

    # Try the title on line 0 alone, then with 1 and 2 wrapped continuation
    # lines appended — the heading never wraps to more than two lines here.
    candidate = m.group(2)
    for extra in range(0, 3):
        joined = " ".join([candidate] + [lines[i] for i in range(1, 1 + extra)
                                         if i < len(lines)])
        if _normalize(joined) == expected:
            # Return the canonical title (clean, de-wrapped) rather than the
            # raw extracted text.
            return m.group(1), _canonical_title(num)
    return None


def _canonical_title(num_norm: str) -> str:
    """Look up the original-cased canonical title for a normalized number."""
    for n, t in KNOWN_CHAPTERS:
        if _normalize(n) == num_norm:
            return t
    return ""


def parse_pdf(pdf_path: str | Path) -> ParsedBook:
    """
    Parse the PDF into chapters with page ranges and per-page text.

    Pass 1: scan every page; a page whose top lines match a known heading starts
            a new chapter. (The TOC page lists all titles inline on one line, so
            its first line won't match a single heading — it's correctly skipped.)
    Pass 2: assign each chapter its page range and concatenate its body text.
    """
    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)

    # Extract once; reuse for both passes.
    pages: list[str] = [p.extract_text() or "" for p in reader.pages]

    # --- Pass 1: find chapter-start pages ---
    starts: list[Chapter] = []
    for i, raw in enumerate(pages):
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        match = _match_heading(lines)
        if match:
            num, title = match
            starts.append(
                Chapter(number=num, index=len(starts) + 1, title=title,
                        start_page=i)
            )

    if not starts:
        raise ValueError(
            "No chapter headings detected. The PDF structure may differ from "
            "the expected format; check parser.KNOWN_CHAPTERS."
        )

    # --- Pass 2: page ranges + body text ---
    for j, ch in enumerate(starts):
        ch.end_page = (starts[j + 1].start_page - 1) if j + 1 < len(starts) else n_pages - 1
        for pg in range(ch.start_page, ch.end_page + 1):
            ch.page_texts.append((pg, pages[pg]))
        ch.text = "\n".join(t for _, t in ch.page_texts)

    return ParsedBook(title="The Adventures of Sherlock Holmes",
                      chapters=starts, n_pages=n_pages)
