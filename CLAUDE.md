# Voice-Grounded PDF Q&A — Project Context

> This file is auto-loaded by Claude Code when a session starts in this folder.
> It carries the project's decisions, architecture, and current status so any
> new session (or teammate) can pick up instantly. Keep it updated as we go.

## What this is

A take-home assignment for the **Wiz.ai AI Builder Intern** role
(submit to `xuanni.teong@wiz.ai`). A web app where a user:

1. Uploads a PDF book (10+ chapters).
2. Asks a question by **microphone**.
3. Gets back a **spoken answer grounded in the document**.

Pipeline: **ASR (speech→text) → RAG (retrieve + generate) → TTS (text→speech)**.

**Timeline:** 4 days, starting 2026-06-25 (deadline ~2026-06-29).

## What the rubric actually rewards (north star)

- **Retrieval quality** — explicitly called out. "Naive fixed-size chunking has
  limited recall; research current methods." This is the make-or-break. We go
  deep here.
- **Distinctive UI/UX** — "avoid the generic AI-template look." UI is weighted.
- **Documented AI-assisted workflow** — the build process itself is a deliverable.
- Graded **holistically**: thoughtful decisions over feature count. Depth > breadth.

## Locked technical decisions (with rationale)

| Area | Choice | Why |
|---|---|---|
| Backend | **Python + FastAPI** | The entire RAG ecosystem (Chroma, rerankers, RAGAS eval) is native to Python. FastAPI feels like Express. |
| Frontend | **React + Vite** | User's strength is web frameworks; this is the part they'll own. |
| ASR | **Deepgram** (REST) | Simple REST API (feels like any web API), $200 free credit, high accuracy, no model hosting. Web Speech API as zero-config fallback. |
| TTS | **Deepgram Aura** | Same provider as ASR — one key, one SDK. ElevenLabs as optional final-demo voice swap. Keep TTS layer pluggable. |
| LLM | **Claude `claude-opus-4-8`** | Most capable; has **native citations** (`citations: {enabled: true}`) → verifiable grounding for free. |
| Vector store | **Chroma** | Simple, local, no infra. |

**User background:** strong in web frameworks, *new to ML/RAG*. Explain concepts
in web terms; recommend rather than offer raw ML options; lean on their React
strength for the UI.

## The retrieval pipeline (the graded centerpiece)

Modeled on **Anthropic's Contextual Retrieval** (cut top-20 retrieval failure
~67% in their benchmark), *improved* by exploiting the known book/chapter
structure that generic enterprise KBs (e.g. Bedrock Knowledge Bases) can't assume.

1. **Chapter-aware parsing** — detect chapter boundaries from PDF structure.
2. **Parent-child chunking** — index small child chunks (~300 tok) for precise
   matching; feed the larger **parent** span (section/chapter) to the LLM for context.
3. **Contextual Retrieval** — prepend an LLM-generated one-line context to each
   chunk before embedding/BM25 (uses Claude + prompt caching to stay cheap).
4. **Hybrid search** — dense vectors + BM25, fused with **Reciprocal Rank Fusion**.
5. **Reranking** — cross-encoder picks the final ~5.
6. **Grounded generation + native citations** (chapter/page).

## Scope (deliberately bounded)

**In:** excellent retrieval, clickable citations (highlight the source passage),
out-of-scope detection ("the book doesn't cover that"). Streaming answers if Day 4 allows.

**Out (on purpose):** multi-turn follow-ups, full chapter-reading view. The rubric
rewards depth; these are where week-long projects spread thin.

## Testing strategy (a graded deliverable)

- **Unit:** chunking boundaries, RRF fusion, chapter detection.
- **Integration:** ingestion pipeline end-to-end on the test PDF.
- **Answer-quality eval:** a RAGAS-style harness (faithfulness, context recall,
  answer relevancy) over a hand-written Q&A set on the test book. This is the
  single most rubric-aligned test — it proves retrieval quality with numbers.

## Build order (each layer independently testable)

- **Day 1 — retrieval core, headless.** Prove answer quality before any voice/UI.
- **Day 2 — FastAPI endpoints + Deepgram ASR/TTS.**
- **Day 3 — React UI** (upload, mic, playback, citation panel).
- **Day 4 — polish (out-of-scope handling), docs, demo video.**

## Current status

**Day 1 COMPLETE — retrieval core, headless, verified.**
- `app/parser.py`: chapter detection by **font size** (headings are larger than
  body text; no hard-coded titles). Reassembles wrapped headings, ignores
  scene-break numerals. 12 chapters, pp.1-227.
- `app/chunker.py`: parent-child chunks (116 parents ~1200 tok, 544 children
  ~300 tok) with chapter/page metadata.
- `app/contextualizer.py`: Anthropic Contextual Retrieval via Haiku + prompt
  caching (6.58M cached tokens vs 147K uncached on the full book).
- `app/indexer.py`: hybrid index — Chroma dense + BM25 over contextualized text.
- `app/retriever.py`: hybrid search → RRF → cross-encoder rerank → parent expansion.
- `app/answerer.py`: Opus 4.8 grounded answers with **native citations** → chapter/page.
- `app/store.py`: JSON persistence for contextualized chunks (per document).
- `tests/`: 14 passing unit tests (parser + chunker).

**Day 2 COMPLETE — API + voice, verified end-to-end.**
- `app/api.py`: FastAPI. `GET /health`, `POST /ask` (text→answer+citations),
  `POST /voice` (audio→ASR→RAG→TTS→JSON w/ transcript, answer, citations, base64 MP3).
  Retriever loaded once at startup (lifespan), shared across requests. CORS for Vite.
- `app/voice.py`: Deepgram ASR (Nova) + Aura TTS over REST; TTS behind a
  pluggable `Synthesizer` protocol; clean `VoiceError` handling.
- Verified: full spoken-question → spoken-answer round-trip works.

**Repo:** https://github.com/yongzhuoyu/pdf-voice-assistant (public). Commits are
feature-split, no Co-Authored-By trailer.

**Build to run the backend:**
- `cd backend && .venv/bin/python scripts/index.py` (once) builds the index.
- `.venv/bin/python -m uvicorn app.api:app --port 8000` serves the API.

**Next up (Day 3): React UI** — upload, mic, playback, citation panel. Frontend
folder is currently empty. Build order: scaffold + text Q&A against /ask first,
then layer mic + /voice on top.

**Keys:** both `ANTHROPIC_API_KEY` and `DEEPGRAM_API_KEY` are in `backend/.env`
(gitignored) and verified working.

## Conventions

- Keep backend code thin and heavily commented — it should read like web code,
  not ML research, so the user can follow it.
- Never commit API keys. Use a `.env` file (gitignored) + `.env.example`.
- Don't truncate document content silently; surface limits instead.
