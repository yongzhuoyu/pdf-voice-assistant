"""
Chunker tests — verify the parent-child invariants the retriever relies on:
every child links to a real parent, chunk sizes land near target, and each
child's cited page falls inside its chapter's page range.
"""

from app import config
from app.chunker import _pack, _split_sentences, _approx_tokens


def test_every_child_links_to_a_real_parent(chunked):
    parent_ids = {p.id for p in chunked.parents}
    assert all(c.parent_id in parent_ids for c in chunked.children)
    # And every parent has at least one child.
    used = {c.parent_id for c in chunked.children}
    assert used == parent_ids


def test_child_pages_within_chapter_ranges(book, chunked):
    ranges = {c.index: (c.start_page, c.end_page) for c in book.chapters}
    for c in chunked.children:
        lo, hi = ranges[c.chapter_index]
        assert lo <= c.page <= hi, f"{c.id} page {c.page} outside {lo}-{hi}"


def test_chunk_sizes_near_target(chunked):
    # Allow generous slack — packing is greedy on sentence edges, not exact.
    child_tokens = [_approx_tokens(c.text) for c in chunked.children]
    parent_tokens = [_approx_tokens(p.text) for p in chunked.parents]
    # No child should blow far past the child target (one big sentence aside).
    assert max(child_tokens) <= config.CHILD_CHUNK_TOKENS * 1.5
    assert max(parent_tokens) <= config.PARENT_CHUNK_TOKENS * 1.5


def test_pack_respects_max_tokens():
    sents = ["word " * 50, "word " * 50, "word " * 50]  # ~65 tokens each
    packed = _pack([s.strip() for s in sents], max_tokens=100)
    # Each 65-token sentence; two would exceed 100, so expect one per chunk.
    assert len(packed) == 3


def test_sentence_splitter_keeps_terminators():
    sents = _split_sentences('He said, "Watch." Then he left! Did he? Yes.')
    assert sents[0].endswith('"') or sents[0].endswith(".")
    assert len(sents) == 4


def test_ids_are_unique(chunked):
    cids = [c.id for c in chunked.children]
    pids = [p.id for p in chunked.parents]
    assert len(cids) == len(set(cids))
    assert len(pids) == len(set(pids))
