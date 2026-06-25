"""
Headless Q&A from the terminal — proves the whole retrieval + answer pipeline
before any voice or UI exists (the Day 1 goal: answer quality first).

Usage:
  python scripts/ask.py "How did Holmes know Watson had been out in the rain?"
  python scripts/ask.py            # interactive prompt loop

Requires the index to be built first:  python scripts/index.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import load_chunks
from app.indexer import load_index
from app.retriever import Retriever
from app.answerer import generate_answer


def answer_question(retriever: Retriever, question: str) -> None:
    t0 = time.time()
    passages = retriever.retrieve(question)
    answer = generate_answer(question, passages)
    dt = time.time() - t0

    print("\n" + "=" * 70)
    print(f"Q: {question}")
    print("-" * 70)
    print(answer.text)
    print("-" * 70)
    if answer.out_of_scope:
        print("[out of scope: the book does not cover this]")
    elif answer.citations:
        print("Citations:")
        seen = set()
        for c in answer.citations:
            key = (c.chapter_number, c.start_page, c.end_page)
            if key in seen:
                continue
            seen.add(key)
            snippet = c.quoted_text.replace("\n", " ")[:70]
            print(f"  - Ch {c.chapter_number} \"{c.chapter_title}\" "
                  f"pp.{c.start_page}-{c.end_page}: \"{snippet}...\"")
    print(f"\nRetrieved {len(passages)} passages in {dt:.1f}s")
    print("=" * 70)


def main() -> None:
    print("Loading index ...")
    chunked = load_chunks()
    index = load_index(chunked)
    retriever = Retriever(index, chunked)
    print("Ready.")

    if len(sys.argv) > 1:
        answer_question(retriever, " ".join(sys.argv[1:]))
        return

    print("Enter a question (blank line to quit).")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        answer_question(retriever, q)


if __name__ == "__main__":
    main()
