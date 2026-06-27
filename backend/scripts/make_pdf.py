"""
Convert the Project Gutenberg plain-text of "The Adventures of Sherlock Holmes"
into a structured PDF with real chapter headings.

Why this exists: the assignment requires a PDF input with 10+ chapters. The
Gutenberg source is plain text, so we render it to PDF *with genuine heading
structure* (large bold chapter titles on their own line) so that our
chapter-aware parsing in the ingestion pipeline has real document structure to
detect — not a flat wall of text.

Run:  python scripts/make_pdf.py
Out:  data/sherlock.pdf
"""

import re
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC = BACKEND_DIR / "data" / "sherlock.txt"        # Gutenberg source text
OUT = BACKEND_DIR.parent / "samples" / "sherlock-holmes.pdf"  # rendered fixture

# A chapter heading looks like "I. A SCANDAL IN BOHEMIA" — a roman numeral,
# a dot, then a TITLE in caps. Bare sub-section markers like "I." (numeral +
# dot, nothing after) are NOT chapter headings, so we require a title.
CHAPTER_RE = re.compile(r"^([IVXL]+)\.\s+([A-Z][A-Z'’\- ]+)$")


def strip_gutenberg_boilerplate(text: str) -> str:
    """Drop the Gutenberg header/footer so only the book remains."""
    start = re.search(r"\*\*\* START OF THE PROJECT GUTENBERG.*?\*\*\*", text, re.S)
    end = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG.*?\*\*\*", text, re.S)
    if start:
        text = text[start.end():]
    if end:
        text = text[: end.start()] if not start else text[: end.start() - start.end()]
    # Re-run end search on the trimmed text to be safe.
    end = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG.*?\*\*\*", text, re.S)
    if end:
        text = text[: end.start()]
    return text.strip()


def build_blocks(text: str):
    """
    Walk the text line by line, grouping it into (kind, content) blocks where
    kind is 'chapter' or 'para'. Blank lines separate paragraphs.
    """
    blocks = []
    para_lines: list[str] = []

    def flush_para():
        if para_lines:
            joined = " ".join(l.strip() for l in para_lines).strip()
            if joined:
                blocks.append(("para", joined))
            para_lines.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        m = CHAPTER_RE.match(line.strip())
        if m:
            flush_para()
            num, title = m.group(1), m.group(2).strip()
            blocks.append(("chapter", f"{num}. {title}"))
        elif line.strip() == "":
            flush_para()
        else:
            para_lines.append(line)
    flush_para()
    return blocks


def main():
    text = strip_gutenberg_boilerplate(SRC.read_text(encoding="utf-8"))
    blocks = build_blocks(text)

    n_chapters = sum(1 for k, _ in blocks if k == "chapter")
    print(f"Detected {n_chapters} chapter headings, {len(blocks)} total blocks.")

    styles = getSampleStyleSheet()
    chapter_style = ParagraphStyle(
        "ChapterHeading",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceBefore=12,
        spaceAfter=18,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=11,
        leading=16,
        spaceAfter=8,
        alignment=4,  # justify
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        title="The Adventures of Sherlock Holmes",
        author="Arthur Conan Doyle",
    )

    story = []
    for i, (kind, content) in enumerate(blocks):
        # XML-escape for reportlab's Paragraph mini-markup.
        safe = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if kind == "chapter":
            if i > 0:
                story.append(PageBreak())
            story.append(Paragraph(safe, chapter_style))
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(safe, body_style))

    doc.build(story)
    print(f"Wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
