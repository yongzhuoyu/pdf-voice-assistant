"""
FastAPI app — exposes the Day 1 retrieval pipeline over HTTP, and (Day 2) adds
voice in/out via Deepgram.

Design note: the retriever loads a cross-encoder reranker and the Chroma index,
which is slow (~seconds). We do that ONCE at startup via the lifespan handler and
stash it on app.state, so every request reuses the warm retriever instead of
re-loading models per call. Think of it like a DB connection pool created at boot.

Endpoints:
  GET  /health        — liveness + whether the index is loaded
  POST /ask           — JSON {question} -> grounded answer + citations (text only)
  POST /voice         — audio file -> ASR -> RAG -> TTS -> spoken answer (Day 2)
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.store import load_chunks, document_info
from app.indexer import load_index
from app.retriever import Retriever
from app.answerer import generate_answer, Answer
from app import voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the index + retriever once at startup; share across requests."""
    chunked = load_chunks()
    index = load_index(chunked)
    app.state.retriever = Retriever(index, chunked)
    app.state.chunked = chunked   # kept for /document metadata
    yield
    # nothing to tear down (Chroma is file-backed)


app = FastAPI(title="PDF Voice Assistant", lifespan=lifespan)

# Allow the React dev server (Day 3) to call us from a different origin.
# Match any localhost port so Vite picking 5173/5174/etc. just works in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---
class AskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    quoted_text: str
    chapter_number: str
    chapter_title: str
    start_page: int
    end_page: int


class AskResponse(BaseModel):
    answer: str
    out_of_scope: bool
    citations: list[CitationOut]


class VoiceResponse(AskResponse):
    """Same as AskResponse plus the recognized question and spoken answer."""

    transcript: str            # what the user said (from ASR)
    audio_base64: str          # MP3 of the answer, base64-encoded
    audio_mime: str = "audio/mpeg"


def _to_response(answer: Answer) -> AskResponse:
    return AskResponse(
        answer=answer.text,
        out_of_scope=answer.out_of_scope,
        citations=[
            CitationOut(
                quoted_text=c.quoted_text,
                chapter_number=c.chapter_number,
                chapter_title=c.chapter_title,
                start_page=c.start_page,
                end_page=c.end_page,
            )
            for c in answer.citations
        ],
    )


# --- Endpoints ---
@app.get("/health")
def health():
    loaded = getattr(app.state, "retriever", None) is not None
    return {"status": "ok", "index_loaded": loaded}


@app.get("/document")
def document():
    """Metadata about the currently-loaded book, for the UI's document context."""
    chunked = getattr(app.state, "chunked", None)
    if chunked is None:
        raise HTTPException(status_code=503, detail="index not loaded")
    return document_info(chunked)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    retriever: Retriever = app.state.retriever
    passages = retriever.retrieve(question)
    answer = generate_answer(question, passages)
    return _to_response(answer)


@app.post("/voice", response_model=VoiceResponse)
async def voice_ask(audio: UploadFile = File(...)):
    """
    Full voice round-trip: spoken question -> ASR -> RAG -> spoken answer.
    Returns the transcript, the grounded answer + citations (for the UI panel),
    and the answer audio as base64 MP3 (for playback).
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty audio upload")

    content_type = audio.content_type or "audio/webm"
    try:
        transcript = voice.transcribe(audio_bytes, content_type=content_type)
    except voice.VoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    if not transcript:
        raise HTTPException(status_code=422,
                            detail="could not transcribe audio; please try again")

    retriever: Retriever = app.state.retriever
    passages = retriever.retrieve(transcript)
    answer = generate_answer(transcript, passages)

    try:
        audio_out = voice.synthesize(answer.text)
    except voice.VoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

    base = _to_response(answer)
    return VoiceResponse(
        **base.model_dump(),
        transcript=transcript,
        audio_base64=base64.b64encode(audio_out).decode("ascii"),
    )
