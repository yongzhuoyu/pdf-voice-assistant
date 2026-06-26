"""
Chapter-aware PDF parser.

Why this is the foundation of retrieval quality: generic RAG treats a PDF as one
flat blob of text. We instead recover the book's real structure — which chapter
each passage belongs to, and what page it's on — so we can (a) feed the LLM the
right *parent* span for context and (b) cite chapter + page in the answer.

How we detect chapters WITHOUT hard-coding the book's titles: a chapter heading
is typeset in a much larger font than the body text (in the test book, 20pt vs
11pt). So we detect headings structurally — "a line whose font is well above the
body-text size" — rather than by matching against a known list. This generalizes
to any PDF that visually distinguishes its headings, and it solves the two
extraction gotchas for free:

  1. Line-wrapped headings ("VII. THE ADVENTURE OF THE BLUE" + "CARBUNCLE"):
     we collect ALL the large-font characters on the page and join them by line,
     so the full title is reassembled regardless of wrapping.

  2. The book reuses "I. II. III." for internal scene breaks: those markers are
     set in normal body font, so they're never flagged as headings. Only the
     genuinely large-font chapter titles are picked up.

If a PDF has an embedded outline (bookmarks), that would be an even cleaner
source; reportlab didn't add one to the test PDF, so font-size detection is the
primary path here.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


# A heading line starts with a roman numeral + dot (e.g. "VII."). Used only to
# confirm a large-font line looks like a chapter heading, not to find chapters.
_HEADING_RE = re.compile(r"^[IVXLCDM]+\.\s")

# A heading's font must exceed body size by at least this many points to count.
_HEADING_SIZE_MARGIN = 4.0


@dataclass
class Chapter:
    """One detected chapter and the text/pages it spans."""

    number: str            # roman numeral, e.g. "VII"
    index: int             # 1-based order in the book
    title: str             # title text, e.g. "THE ADVENTURE OF THE BLUE CARBUNCLE"
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


def _body_font_size(pdf: "pdfplumber.PDF") -> float:
    """
    Estimate the body-text font size as the most common character size across a
    sample of pages. Headings are then anything well above this.
    """
    sizes: list[float] = []
    for pg in pdf.pages[: min(len(pdf.pages), 10)]:
        sizes.extend(round(c["size"], 1) for c in pg.chars)
    if not sizes:
        return 11.0
    return statistics.mode(sizes)


def _heading_on_page(page: "pdfplumber.page.Page", min_size: float) -> str | None:
    """
    Return the reassembled large-font heading text on this page, or None.

    Collects every character at/above `min_size`, groups them into lines by their
    vertical position, orders the lines top-to-bottom, and joins them with spaces.
    This reassembles a wrapped title ("...BLUE" / "CARBUNCLE") into one string.
    """
    big = [c for c in page.chars if c["size"] >= min_size]
    if not big:
        return None

    # Group characters into lines by rounded vertical position.
    lines: dict[int, list[dict]] = {}
    for c in big:
        lines.setdefault(round(c["top"]), []).append(c)

    line_texts: list[str] = []
    for top in sorted(lines):
        chars = sorted(lines[top], key=lambda c: c["x0"])
        line_texts.append("".join(c["text"] for c in chars).strip())

    heading = " ".join(t for t in line_texts if t).strip()
    heading = re.sub(r"\s+", " ", heading)
    return heading or None


def _split_number_title(heading: str) -> tuple[str, str] | None:
    """Split 'VII. THE ADVENTURE...' into ('VII', 'THE ADVENTURE...')."""
    if not _HEADING_RE.match(heading):
        return None
    num, _, title = heading.partition(".")
    return num.strip(), title.strip()


def parse_pdf(pdf_path: str | Path) -> ParsedBook:
    """
    Parse the PDF into chapters with page ranges and per-page text.

    Pass 1: detect chapter-start pages by finding large-font headings (pdfplumber
            gives per-character font sizes; pypdf does not).
    Pass 2: assign each chapter its page range and concatenate its body text
            (pypdf's text extraction is used for the body, matching what the rest
            of the pipeline indexes).
    """
    pdf_path = str(pdf_path)

    # --- Pass 1: detect headings by font size ---
    starts: list[Chapter] = []
    with pdfplumber.open(pdf_path) as pdf:
        body = _body_font_size(pdf)
        min_heading = body + _HEADING_SIZE_MARGIN
        for i, page in enumerate(pdf.pages):
            heading = _heading_on_page(page, min_heading)
            if not heading:
                continue
            split = _split_number_title(heading)
            if not split:
                continue
            num, title = split
            starts.append(
                Chapter(number=num, index=len(starts) + 1, title=title, start_page=i)
            )

    if not starts:
        raise ValueError(
            "No chapter headings detected. This PDF may not visually distinguish "
            "headings by font size; consider an outline- or TOC-based parser."
        )

    # --- Pass 2: page ranges + body text (via pypdf) ---
    reader = PdfReader(pdf_path)
    n_pages = len(reader.pages)
    pages = [p.extract_text() or "" for p in reader.pages]

    for j, ch in enumerate(starts):
        ch.end_page = (starts[j + 1].start_page - 1) if j + 1 < len(starts) else n_pages - 1
        for pg in range(ch.start_page, ch.end_page + 1):
            ch.page_texts.append((pg, pages[pg]))
        ch.text = "\n".join(t for _, t in ch.page_texts)

    return ParsedBook(title="The Adventures of Sherlock Holmes",
                      chapters=starts, n_pages=n_pages)
