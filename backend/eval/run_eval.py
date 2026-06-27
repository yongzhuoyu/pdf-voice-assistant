"""
Answer-quality evaluation harness (RAGAS-style).

The assignment's make-or-break criterion is retrieval quality: "answers must be
genuinely usable." A green unit-test suite proves the chunker splits correctly;
it does NOT prove the system answers questions well. This harness does — it runs
a hand-written question set (eval/qa_set.json) end-to-end through the real
retrieval + generation pipeline and scores four metrics, the same dimensions the
RAGAS framework measures, computed here without the heavy RAGAS dependency:

  - Context Recall (retrieval)  : did retrieval surface the passage that holds
                                  the answer? Scored deterministically by checking
                                  whether the expected chapter is in the retrieved
                                  top-k. This is the purest signal of retrieval
                                  quality, the rubric's centerpiece.
  - Answer Correctness          : does the generated answer contain the expected
                                  fact? Scored by an LLM judge (claude-opus-4-8).
  - Faithfulness (grounding)    : is every claim in the answer supported by the
                                  retrieved passages, with no invented detail?
                                  Scored by an LLM judge.
  - Out-of-scope Accuracy       : for questions the book cannot answer, did the
                                  system correctly refuse (out_of_scope flag)
                                  instead of hallucinating? Scored deterministically.

Why an LLM judge: correctness and faithfulness are semantic, not string-equality
("two centuries" vs "more than 200 years" are both right). Using a strong model
as judge is exactly how RAGAS scores these; we make the judging prompt strict and
ask for a 0/1 verdict plus a one-line reason so every score is auditable.

Run (index is built fresh from the sample PDF, so it works from a clean checkout):

    cd backend && .venv/bin/python -m eval.run_eval

Cost note: this makes one generation call + two judge calls per question, on top
of a one-time contextualization of the sample book. The sample is small, so a
full run is a few cents.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic

from app import config
from app.parser import parse_pdf
from app.chunker import chunk_book
from app.contextualizer import contextualize
from app.indexer import build_index
from app.retriever import Retriever
from app.answerer import generate_answer, Answer

EVAL_DIR = Path(__file__).resolve().parent
QA_PATH = EVAL_DIR / "qa_set.json"
RESULTS_PATH = EVAL_DIR / "results.json"

# Dedicated Chroma collection id so the eval never collides with uploaded books.
EVAL_DOC_ID = "eval-lighthouses"


# --- Pipeline setup -------------------------------------------------------

def build_retriever(pdf_path: Path) -> Retriever:
    """Parse -> chunk -> contextualize -> index the sample book, return a Retriever."""
    print(f"Building index from {pdf_path.name} ...")
    t0 = time.time()
    book = parse_pdf(pdf_path)
    chunked = chunk_book(book)
    contextualize(book, chunked, progress=False)
    index = build_index(chunked, document_id=EVAL_DOC_ID)
    print(f"Indexed {len(chunked.children)} children / {len(chunked.parents)} parents "
          f"in {time.time() - t0:.1f}s\n")
    return Retriever(index, chunked)


# --- LLM judges -----------------------------------------------------------

def _judge_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.require_anthropic_key())


def _ask_judge(client: anthropic.Anthropic, prompt: str) -> tuple[int, str]:
    """Ask the judge for a strict 0/1 verdict and a one-line reason."""
    resp = client.messages.create(
        model=config.ANSWER_MODEL,
        max_tokens=200,
        system=(
            "You are a strict evaluation judge. Reply with a single line in the "
            "exact form: SCORE | reason. SCORE is 1 if the criterion is fully met "
            "and 0 otherwise. Be conservative: when in doubt, score 0."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    head, _, reason = text.partition("|")
    score = 1 if head.strip().startswith("1") else 0
    return score, reason.strip() or text


def judge_correctness(client, question, expected, actual) -> tuple[int, str]:
    return _ask_judge(client, (
        f"Question: {question}\n"
        f"Reference answer (ground truth): {expected}\n"
        f"Generated answer: {actual}\n\n"
        "Criterion: does the generated answer convey the same key fact as the "
        "reference answer? Ignore wording, length, and extra correct detail. "
        "Score 1 if the core fact matches, 0 if it is wrong, missing, or contradicts."
    ))


def judge_faithfulness(client, answer, passages_text) -> tuple[int, str]:
    return _ask_judge(client, (
        "Source passages the answer must be grounded in:\n"
        f"\"\"\"\n{passages_text}\n\"\"\"\n\n"
        f"Generated answer:\n{answer}\n\n"
        "Criterion: is every factual claim in the generated answer supported by "
        "the source passages above, with no invented or outside information? "
        "Score 1 if fully grounded, 0 if any claim is unsupported."
    ))


# --- Eval loop ------------------------------------------------------------

def run() -> dict:
    qa = json.loads(QA_PATH.read_text(encoding="utf-8"))
    pdf_path = config.BACKEND_DIR.parent / qa["source_pdf"]
    if not pdf_path.exists():
        sys.exit(f"Sample PDF not found at {pdf_path}")

    retriever = build_retriever(pdf_path)
    judge = _judge_client()

    rows = []
    for item in qa["items"]:
        q = item["question"]
        passages = retriever.retrieve(q)
        answer: Answer = generate_answer(q, passages)
        retrieved_chapters = [p.chapter_number for p in passages]

        row = {
            "id": item["id"],
            "kind": item["kind"],
            "question": q,
            "answer": answer.text,
            "out_of_scope": answer.out_of_scope,
            "retrieved_chapters": retrieved_chapters,
            "n_citations": len(answer.citations),
        }

        if item["kind"] == "in_scope":
            # Context recall: deterministic — expected chapter present in top-k.
            row["context_recall"] = int(item["expected_chapter"] in retrieved_chapters)
            # Correctness + faithfulness: LLM judge.
            c_score, c_why = judge_correctness(judge, q, item["expected_answer"], answer.text)
            passages_text = "\n\n---\n\n".join(p.text for p in passages)
            f_score, f_why = judge_faithfulness(judge, answer.text, passages_text)
            row.update({
                "correctness": c_score, "correctness_reason": c_why,
                "faithfulness": f_score, "faithfulness_reason": f_why,
            })
        else:
            # Out-of-scope: the system passes if it refused (flagged out_of_scope).
            row["refused_correctly"] = int(answer.out_of_scope)

        rows.append(row)
        _print_row(row)

    summary = _summarize(rows)
    out = {"book": qa["book"], "summary": summary, "rows": rows}
    RESULTS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(summary)
    print(f"\nFull results written to {RESULTS_PATH.relative_to(config.BACKEND_DIR)}")
    return out


def _mean(xs: list[int]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def _summarize(rows: list[dict]) -> dict:
    in_scope = [r for r in rows if r["kind"] == "in_scope"]
    oos = [r for r in rows if r["kind"] == "out_of_scope"]
    return {
        "n_in_scope": len(in_scope),
        "n_out_of_scope": len(oos),
        "context_recall": _mean([r["context_recall"] for r in in_scope]),
        "answer_correctness": _mean([r["correctness"] for r in in_scope]),
        "faithfulness": _mean([r["faithfulness"] for r in in_scope]),
        "out_of_scope_accuracy": _mean([r["refused_correctly"] for r in oos]),
    }


def _print_row(r: dict) -> None:
    if r["kind"] == "in_scope":
        print(f"  [{r['id']}] recall={r['context_recall']} "
              f"correct={r['correctness']} faithful={r['faithfulness']} "
              f"chapters={r['retrieved_chapters']}")
    else:
        verdict = "refused" if r["refused_correctly"] else "ANSWERED (bad)"
        print(f"  [{r['id']}] out-of-scope -> {verdict}")


def _print_summary(s: dict) -> None:
    print("\n" + "=" * 52)
    print("ANSWER-QUALITY EVALUATION")
    print("=" * 52)
    print(f"In-scope questions     : {s['n_in_scope']}")
    print(f"Out-of-scope questions : {s['n_out_of_scope']}")
    print("-" * 52)
    print(f"Context recall         : {s['context_recall']:.0%}")
    print(f"Answer correctness     : {s['answer_correctness']:.0%}")
    print(f"Faithfulness           : {s['faithfulness']:.0%}")
    print(f"Out-of-scope accuracy  : {s['out_of_scope_accuracy']:.0%}")
    print("=" * 52)


if __name__ == "__main__":
    run()
