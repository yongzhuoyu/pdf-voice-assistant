# Testing & Acceptance Strategy

The assignment asks for "a clear testing/acceptance strategy (unit, integration,
end-to-end, and/or answer-quality evaluation)." This project uses all four,
because each proves something the others cannot:

| Layer | Proves | Where |
|---|---|---|
| **Unit tests** | The deterministic building blocks are correct (chapter detection, chunk boundaries). | `backend/tests/` |
| **Integration** | The ingestion pipeline runs end-to-end and produces a queryable index. | eval harness setup + manual upload |
| **End-to-end** | The live HTTP API behaves correctly across the real request paths. | manual API drive (documented below) |
| **Answer-quality evaluation** | Retrieval and generation are *genuinely usable* — measured, not asserted. | `backend/eval/` |

The key idea: a green unit suite proves the chunker splits text correctly. It
does **not** prove the system answers questions well. That is what the
answer-quality evaluation is for, and it is the layer most aligned with how the
assignment is graded.

---

## 1. Unit tests

Fast, deterministic, no network or API keys. They cover the two stages where a
subtle bug would silently degrade every downstream answer: **chapter detection**
and **chunking**.

**Parser (8 tests)** — detects exactly the right number of chapters, keeps them
in order, produces contiguous page ranges that cover the book, reassembles
headings that wrap across lines, and does *not* mistake scene-break numerals for
chapter headings.

**Chunker (6 tests)** — every child chunk links back to a real parent, child
page numbers fall within their chapter's range, chunk sizes land near the target,
the packer never exceeds the max token budget, the sentence splitter keeps its
terminators, and all chunk IDs are unique.

Run them:

```bash
cd backend && .venv/bin/python -m pytest -q
```

Expected: **14 passed**. A session-scoped fixture parses and chunks the bundled
book once and shares it across tests, so the suite stays fast.

---

## 2. Integration

The ingestion pipeline is exercised end-to-end whenever a book is indexed: parse
→ chunk → contextualize → build dense + BM25 index. The evaluation harness
(below) rebuilds this pipeline from the sample PDF on every run, so a successful
eval run *is* an integration test of ingestion — if any stage broke, the harness
would fail to produce a queryable index before it ever scored an answer.

Indexing a real book through the live system (upload → background job → ready)
also covers the registry, progress reporting, and per-document Chroma collection.

---

## 3. End-to-end (live API)

The HTTP surface is verified by driving the running server through the real
request paths, exactly as the frontend would. This is the layer that catches
seam bugs unit tests miss — page-number off-by-ones, empty-library handling,
duplicate uploads, the out-of-scope flag.

With the backend running (`uvicorn app.api:app --port 8000`):

| Path | Expected behavior |
|---|---|
| `GET /health` | `{"status":"ok"}`. |
| `GET /document` (empty library) | `{"id":null}` with 200 — an empty library is a valid state, not an error. |
| `POST /documents` (PDF) | Returns an id immediately; status moves `indexing` → `ready`. |
| `POST /documents` (same PDF again) | Returns the existing doc with `duplicate:true`; does not re-index. |
| `GET /document?doc_id=…` | Correct title, chapter list, and page count for *that* book. |
| `POST /ask` (in-scope) | Grounded answer, ≥1 citation, `out_of_scope:false`. |
| `POST /ask` (out-of-scope) | "The book does not cover…", 0 citations, `out_of_scope:true`. |
| `POST /voice` (audio) | Transcript + answer + citations + base64 MP3. |
| `DELETE /documents/{id}` | Removes the registry entry, files, and Chroma collection. |

These were verified manually against a live instance; the table doubles as a
regression checklist.

---

## 4. Answer-quality evaluation (the centerpiece)

`backend/eval/` contains a **RAGAS-style** evaluation harness. It runs a
hand-written question set through the real retrieval + generation pipeline and
scores four metrics — the same dimensions RAGAS measures, computed here without
the heavy RAGAS dependency.

### Metrics

| Metric | What it measures | How it is scored |
|---|---|---|
| **Context recall** | Did retrieval surface the passage that holds the answer? | Deterministic — is the expected chapter in the retrieved top-k? |
| **Answer correctness** | Does the answer convey the right fact? | LLM judge (claude-opus-4-8), strict 0/1 verdict. |
| **Faithfulness** | Is every claim supported by the retrieved passages, with nothing invented? | LLM judge. |
| **Out-of-scope accuracy** | For unanswerable questions, did the system refuse instead of hallucinating? | Deterministic — did the `out_of_scope` flag fire? |

Context recall is the purest signal of **retrieval quality** — the thing the
rubric weighs most — and it is scored deterministically so it cannot be flattered
by a generous judge. Correctness and faithfulness are semantic ("two centuries"
and "more than 200 years" are both right), so they use a strong model as judge,
which is exactly how RAGAS scores them. Every judged verdict is saved with a
one-line reason in `eval/results.json`, so scores are auditable rather than
opaque.

### The question set

`eval/qa_set.json` holds 12 hand-written questions over the bundled 12-chapter
sample book: 10 in-scope (each with a reference answer and the chapter that
contains it) and 2 out-of-scope (plausible-sounding but unanswerable, to test
refusal).

### Running it

```bash
cd backend && .venv/bin/python -m eval.run_eval
```

The harness builds a fresh index from the sample PDF (so it works from a clean
checkout), runs every question, scores it, prints a summary, and writes full
per-question results to `eval/results.json`. It needs the Anthropic key set.

### Results

The most recent run scored:

```
====================================================
ANSWER-QUALITY EVALUATION
====================================================
In-scope questions     : 10
Out-of-scope questions : 2
----------------------------------------------------
Context recall         : 100%
Answer correctness     : 100%
Faithfulness           : 100%
Out-of-scope accuracy  : 100%
====================================================
```

In every in-scope question, the chapter containing the answer was retrieved — and
in each case it ranked **first** among the retrieved passages, which is stronger
evidence than recall alone: the pipeline is not just including the right passage,
it is ranking it at the top.

### Honest reading of the numbers

A perfect score should be read with the corpus in mind. The sample book was
written to be a clean test bed — 12 single-page, self-contained chapters, each
with distinct, concrete facts — so it is a *favorable* case, not proof the system
is flawless on arbitrary PDFs. What the run genuinely demonstrates is that the
full pipeline (contextualization, hybrid search, RRF, reranking, grounded
generation, and out-of-scope refusal) works end-to-end and that no stage is
silently broken. A harder evaluation set — longer chapters, questions whose
answers span multiple chapters, near-duplicate distractor passages — is the
natural next step to find the pipeline's actual ceiling, and the harness is built
to take a larger `qa_set.json` without code changes.
