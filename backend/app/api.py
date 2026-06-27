"""
FastAPI app — exposes the retrieval pipeline over HTTP, with voice in/out and
multi-document (upload-your-own-book) support.

Design notes:
- Retrievers are expensive to load (cross-encoder + Chroma collection), so we
  cache one per document and reuse it across requests, loading lazily on first
  use. Think of it like a connection pool, keyed by document.
- Uploading a book kicks off indexing in a BACKGROUND thread (it takes minutes —
  one LLM call per chunk). The upload request returns immediately with a document
  id; the UI polls /documents/{id} for progress.

Endpoints:
  GET  /health                 — liveness
  GET  /documents              — list all books + their indexing status
  POST /documents              — upload a PDF, start background indexing
  GET  /documents/{id}         — one book's status/progress
  GET  /document?doc_id=...    — metadata (title, chapters, pages) for a book
  POST /ask     {question, doc_id?}      — grounded answer + citations (text)
  POST /voice   (audio, doc_id?)         — spoken question -> spoken answer
"""

from __future__ import annotations

import base64
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import config, library, voice
from app.retriever import Retriever
from app.answerer import generate_answer, Answer


# --- Retriever cache (one per document, lazy-loaded) ---
class RetrieverCache:
    def __init__(self):
        self._by_doc: dict[str, tuple] = {}   # doc_id -> (Retriever, chunked, info)
        self._lock = threading.Lock()

    def get(self, doc_id: str):
        with self._lock:
            if doc_id in self._by_doc:
                return self._by_doc[doc_id]
        rec = library.get_document(doc_id)
        if not rec or rec.status != library.STATUS_READY:
            raise HTTPException(status_code=409, detail="document is not ready")
        chunked, index = library.load_document(doc_id)
        retriever = Retriever(index, chunked)
        info = library.document_info_for(doc_id, chunked, rec.title, rec.n_pages)
        with self._lock:
            self._by_doc[doc_id] = (retriever, chunked, info)
        return self._by_doc[doc_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail any indexing jobs orphaned by a previous restart, then register the
    # bundled Sherlock book so the app has something ready without an upload.
    library.recover_orphaned_jobs()
    library.ensure_seed_document()
    app.state.cache = RetrieverCache()
    yield


app = FastAPI(title="PDF Voice Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---
class AskRequest(BaseModel):
    question: str
    doc_id: str | None = None


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
    transcript: str
    audio_base64: str
    audio_mime: str = "audio/mpeg"


def _to_response(answer: Answer) -> AskResponse:
    return AskResponse(
        answer=answer.text,
        out_of_scope=answer.out_of_scope,
        citations=[
            CitationOut(
                quoted_text=c.quoted_text, chapter_number=c.chapter_number,
                chapter_title=c.chapter_title, start_page=c.start_page,
                end_page=c.end_page,
            )
            for c in answer.citations
        ],
    )


def _resolve_doc_id(doc_id: str | None) -> str:
    """Use the given doc, or fall back to the most recent ready document."""
    if doc_id:
        return doc_id
    for rec in library.list_documents():
        if rec.status == library.STATUS_READY:
            return rec.id
    raise HTTPException(status_code=409, detail="no document is ready yet")


# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documents")
def documents():
    return [vars(r) for r in library.list_documents()]


@app.get("/documents/{doc_id}")
def document_status(doc_id: str):
    rec = library.get_document(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="document not found")
    return vars(rec)


@app.post("/documents")
async def upload_document(file: UploadFile = File(...), title: str | None = Form(None)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="please upload a .pdf file")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    # Size guard.
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF is too large (max {config.MAX_UPLOAD_MB} MB).",
        )

    # Page-count guard + that it's a readable PDF at all.
    import io
    from pypdf import PdfReader
    try:
        n_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        raise HTTPException(status_code=400, detail="could not read this PDF.")
    if n_pages > config.MAX_UPLOAD_PAGES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF has too many pages ({n_pages}; max {config.MAX_UPLOAD_PAGES}).",
        )

    doc_id = library.create_document(pdf_bytes, file.filename, title=title)
    # Index in the background so the request returns immediately.
    threading.Thread(target=library.build_document, args=(doc_id,), daemon=True).start()
    return {"id": doc_id, "status": library.STATUS_INDEXING}


@app.get("/document")
def document(doc_id: str | None = None):
    doc_id = _resolve_doc_id(doc_id)
    _, _, info = app.state.cache.get(doc_id)
    return {"id": doc_id, **info}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    doc_id = _resolve_doc_id(req.doc_id)
    retriever, _, _ = app.state.cache.get(doc_id)
    passages = retriever.retrieve(question)
    answer = generate_answer(question, passages)
    return _to_response(answer)


@app.post("/voice", response_model=VoiceResponse)
async def voice_ask(audio: UploadFile = File(...), doc_id: str | None = Form(None)):
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

    doc_id = _resolve_doc_id(doc_id)
    retriever, _, _ = app.state.cache.get(doc_id)
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
