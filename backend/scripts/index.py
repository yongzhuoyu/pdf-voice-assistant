"""
Build the search index from the test PDF, end to end.

  parse PDF -> chapter-aware chunks -> contextualize (Claude) -> persist JSON
            -> build Chroma dense index (+ BM25 in memory)

Run once:  python scripts/index.py
Re-run with --skip-context to rebuild only the dense index from the cached
contextualized chunks (no API cost), e.g. after tweaking embeddings.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.parser import parse_pdf
from app.chunker import chunk_book
from app.contextualizer import contextualize
from app.indexer import build_index
from app.store import save_chunks, load_chunks, CHUNKS_PATH


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skip-context", action="store_true",
        help="Reuse cached contextualized chunks (no API calls); rebuild dense index only.",
    )
    args = ap.parse_args()

    if args.skip_context:
        print(f"Loading cached chunks from {CHUNKS_PATH} ...")
        chunked = load_chunks()
    else:
        print(f"Parsing {config.TEST_PDF} ...")
        book = parse_pdf(config.TEST_PDF)
        print(f"  {len(book.chapters)} chapters, {book.n_pages} pages")

        print("Chunking ...")
        chunked = chunk_book(book)
        print(f"  {len(chunked.parents)} parents, {len(chunked.children)} children")

        print(f"Contextualizing {len(chunked.children)} chunks with {config.CONTEXT_MODEL} ...")
        t0 = time.time()
        contextualize(book, chunked)
        print(f"  contextualization took {time.time()-t0:.0f}s")

        path = save_chunks(chunked)
        print(f"  saved contextualized chunks -> {path}")

    print("Building dense (Chroma) index ...")
    build_index(chunked)
    print(f"  Chroma persisted -> {config.CHROMA_DIR}")
    print("Index build complete.")


if __name__ == "__main__":
    main()
