# AI-Assisted Workflow

The assignment asks for "a disciplined AI-assisted workflow" and looks at "the
critical judgment you apply when working with AI, and how effectively you prompt
to reach a strong result in fewer iterations." This document is an honest account
of how this project was actually built with an AI coding assistant (Claude Code) —
including the places where the right move was to *overrule* it.

The short version: the AI was used as a fast, knowledgeable pair-programmer, not
as an autopilot. Every architectural decision, every rejection of a lazy
solution, and every "that's not good enough" was a human judgment call. The
git history (39 feature-split commits) is the audit trail.

---

## Principles that guided the collaboration

**1. Decide the architecture first, then let the AI implement within it.**
The retrieval design — Contextual Retrieval, parent-child chunking, hybrid search
with RRF and reranking — was chosen deliberately and up front (see the
[ADRs](./adr/)), based on the assignment's explicit hint that naive chunking has
poor recall. The AI then implemented each stage. This ordering matters: handing
an AI a vague "build a RAG system" prompt yields a generic fixed-size-chunk
pipeline, which is exactly what the rubric warns against. The strong result came
from constraining the AI with a researched design, not from asking it to invent
one.

**2. Build in independently testable layers.**
Work proceeded retrieval core → API → voice → UI → polish, each layer proven
before the next was started. The retrieval core was validated headless (does it
answer well?) before any voice or UI existed, so quality problems surfaced where
they were cheap to fix rather than buried under a stack of later features.

**3. Commit by feature, with honest messages.**
Each commit is one coherent change (`Chapter-aware PDF parser`, `Parallelize
contextualization`, `Fix contradictory out-of-scope flag`). This keeps the
history reviewable and forces each unit of AI-generated work to be understood and
accepted on its own, rather than rubber-stamped in a giant blob.

**4. Verify by running the thing, not by trusting that it compiles.**
The standard for "done" was driving the live app to the changed behavior and
observing it — uploading a real PDF, asking a real question, watching the
citation render — not just a green test run. Several bugs below were caught only
because of this.

---

## Where human judgment overruled the AI

These are the moments that mattered most — where accepting the AI's first answer
would have produced a worse result.

**Hard-coded chapter titles → font-size detection.**
An early parser implementation leaned on recognizing specific chapter-title
patterns. That would have broken on any other book. The fix was to reject the
shortcut entirely and require a *general* method: detect headings by font size
(headings are set larger than body text), with no list of expected titles. This
is the difference between a demo that works on one PDF and a system that works on
the assignment's actual requirement ("upload a PDF book").
→ commit `Detect chapters by font size, not a hard-coded title list`

**"Index ready" and other developer jargon in the UI.**
The AI's UI copy leaked implementation language — an "indexed / Index ready"
status that means nothing to an end user. This was flagged and removed: end users
do not know what an index is. Documentation and UI both have to speak the reader's
language, not the implementer's.
→ commits `Remove dev jargon and the 'Ready' status indicator from the UI`

**The generic "AI-template" look.**
The first UI was clean but generic — exactly the look the rubric tells you to
avoid. It was redesigned into a distinctive "Bold Editorial" theme. An AI will
happily produce a competent, forgettable interface; recognizing that "competent
but generic" fails this particular brief was a human call.
→ commit `Redesign UI: Bold Editorial theme`

**Non-deterministic out-of-scope handling, then a contradictory banner.**
The first out-of-scope detection guessed from the answer prose. That was replaced
with a deterministic scope tag the model must emit. Then a subtler bug appeared: a
"Not covered" banner rendered above an answer that clearly *did* discuss the
topic, because the book covered it only partially. The rule was refined to flag
out-of-scope only when the model both tags it *and* cites nothing. This is the
kind of correctness nuance an AI does not volunteer — it came from looking
critically at the rendered output.
→ commits `Make out-of-scope detection deterministic via a scope tag`,
`Fix contradictory out-of-scope flag`

**14-minute indexing was unacceptable, so it was re-engineered.**
Contextualizing a full book ran sequentially and took ~14 minutes. Rather than
accept it, the contextualizer was parallelized while *preserving* the prompt-cache
behavior that keeps it cheap (warm the cache with the first chunk, then fan the
rest out concurrently). This cut indexing by roughly an order of magnitude.
→ commit `Parallelize contextualization (~14min -> ~2min for a full book)`

**"Why are there so many bugs surfacing?"**
At one point small UI bugs kept appearing (a stale browser-tab title, a leftover
Vite favicon). The corrective feedback was to be more *meticulous* — verify the
whole experience (tab title, favicon, copy, every UI state), not just that the
feature functions, and to flag uncertainties up front. This raised the
verification bar for the rest of the project and is why the final production
audit was thorough rather than cursory.

---

## The production-readiness audit

Before writing this documentation, the whole codebase was reviewed for
production-readiness with the AI, specifically hunting for dead code, duplication,
and code smells. This found real issues that a "looks done" pass would have
missed:

- A latent bug where `document_info()` returned the *test fixture's* title and
  page count for every uploaded book, masked only because a caller happened to
  override both values. Fixed to derive only what the data actually supports.
- A `.gitignore` defect: an inline comment on the `backend/data/docs/` line meant
  git never actually ignored it, so user-uploaded books could have been
  committed. Caught during the commit step and fixed.
- Dead code: orphaned dev scripts from an earlier single-book design, an unused
  config constant, and unused imports — all removed.

→ commits `Fix document_info fixture leakage…`, `Remove orphaned dev scripts, fix
gitignore defect…`, `Hoist function-level imports and remove unused import`

The lesson reflected throughout: an AI is excellent at producing working code
quickly, but "working" and "production-ready" are different bars. Closing that gap
is a human responsibility, and it is where critical judgment shows up most.

---

## What effective prompting looked like here

- **Specify the standard, not just the task.** "Build documentation" yields slop;
  "follow the documentation patterns of repos praised for it — Diátaxis for
  structure, Nygard ADRs for decisions — with full technical depth but readable
  by a newcomer" yields something usable. The same was true for code: naming the
  design constraint (no hard-coded titles, deterministic scope detection) reached
  a strong result in fewer iterations than open-ended prompts.
- **Make the AI explain before it builds.** Concepts (what RAG is, why
  contextualization helps) were worked through deliberately, so that accepting or
  rejecting an implementation was an informed decision rather than a leap of
  faith.
- **Treat AI output as a draft to review, never as a finished artifact.** Every
  episode above is an instance of reading the output critically and sending it
  back.
