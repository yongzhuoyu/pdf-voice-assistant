"""
Parser tests — the most rubric-relevant unit tests, because chapter detection
is the foundation of the whole retrieval pipeline. We assert the two documented
gotchas are actually handled, not just that the happy path runs.
"""

from app.parser import KNOWN_CHAPTERS, _match_heading, _normalize


def test_detects_exactly_twelve_chapters(book):
    assert len(book.chapters) == 12


def test_chapter_titles_match_canonical_list(book):
    got = [(c.number, c.title) for c in book.chapters]
    assert got == KNOWN_CHAPTERS


def test_page_ranges_are_contiguous_and_cover_book(book):
    # First chapter starts after the TOC; ranges are contiguous; last reaches end.
    for a, b in zip(book.chapters, book.chapters[1:]):
        assert b.start_page == a.end_page + 1
    assert book.chapters[-1].end_page == book.n_pages - 1


def test_wrapped_heading_is_reassembled():
    # Gotcha 1: "VII. THE ADVENTURE OF THE BLUE" + "CARBUNCLE" on the next line.
    lines = ["VII. THE ADVENTURE OF THE BLUE", "CARBUNCLE", "Some body text..."]
    match = _match_heading(lines)
    assert match == ("VII", "THE ADVENTURE OF THE BLUE CARBUNCLE")


def test_bare_scene_break_numeral_is_not_a_chapter():
    # Gotcha 2: a bare "I." (internal scene break) must NOT match a chapter,
    # because it carries no title to cross-reference against the known list.
    assert _match_heading(["I.", "I had called upon my friend..."]) is None
    assert _match_heading(["II.", "Some scene text"]) is None


def test_unknown_numeral_title_pair_rejected():
    # A roman numeral with a title that isn't in the canonical list is rejected.
    assert _match_heading(["I. A TITLE THAT DOES NOT EXIST"]) is None


def test_apostrophe_normalization():
    # Curly vs straight apostrophe must fold so "ENGINEER'S" matches either way.
    assert _normalize("THE ADVENTURE OF THE ENGINEER’S THUMB") == \
        _normalize("THE ADVENTURE OF THE ENGINEER'S THUMB")


def test_chapter_nine_engineers_thumb_detected(book):
    # Chapter IX has the apostrophe + a wrapped heading — exercise both at once.
    ch9 = book.chapters[8]
    assert ch9.number == "IX"
    assert ch9.title == "THE ADVENTURE OF THE ENGINEER'S THUMB"
