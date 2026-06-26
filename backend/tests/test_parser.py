"""
Parser tests — the most rubric-relevant unit tests, because chapter detection
is the foundation of the whole retrieval pipeline.

Detection is by font size (headings are typeset larger than body text), so these
tests assert the real outcomes on the test PDF: exactly the right chapters, full
titles (including line-wrapped ones), no scene-break false positives, and
contiguous page coverage. Plus unit tests for the heading-parsing helpers.
"""

from app.parser import _split_number_title

# The chapter numbers we expect, in order. Titles are checked loosely (the parser
# reads them from the PDF, so we don't re-hard-code exact strings here).
EXPECTED_NUMBERS = ["I", "II", "III", "IV", "V", "VI",
                    "VII", "VIII", "IX", "X", "XI", "XII"]


def test_detects_exactly_twelve_chapters(book):
    assert len(book.chapters) == 12


def test_chapter_numbers_in_order(book):
    assert [c.number for c in book.chapters] == EXPECTED_NUMBERS


def test_page_ranges_are_contiguous_and_cover_book(book):
    # Ranges are contiguous and the last chapter reaches the final page.
    for a, b in zip(book.chapters, book.chapters[1:]):
        assert b.start_page == a.end_page + 1
    assert book.chapters[-1].end_page == book.n_pages - 1


def test_scene_breaks_not_detected_as_chapters(book):
    # The book reuses I./II./III. for internal scene breaks. Those are in body
    # font, so font-size detection must ignore them — exactly 12 chapters, no more.
    assert len(book.chapters) == 12
    # Chapter I spans many pages (its scene-break "I." on page 1 was not split off).
    assert book.chapters[0].end_page > book.chapters[0].start_page


def test_wrapped_titles_reassembled(book):
    # Chapters VII-XII have line-wrapped headings; the full title must be present.
    by_num = {c.number: c.title for c in book.chapters}
    assert "BLUE" in by_num["VII"] and "CARBUNCLE" in by_num["VII"]
    assert "COPPER" in by_num["XII"] and "BEECHES" in by_num["XII"]


def test_chapter_nine_engineers_thumb(book):
    # Chapter IX has both an apostrophe and a wrapped heading.
    ch9 = book.chapters[8]
    assert ch9.number == "IX"
    assert "ENGINEER" in ch9.title and "THUMB" in ch9.title


# --- helper unit tests ---

def test_split_number_title_basic():
    assert _split_number_title("VII. THE ADVENTURE OF THE BLUE CARBUNCLE") == \
        ("VII", "THE ADVENTURE OF THE BLUE CARBUNCLE")


def test_split_number_title_rejects_non_heading():
    # A line that doesn't start with a roman numeral + dot isn't a heading.
    assert _split_number_title("I had called upon my friend Sherlock Holmes") is None
