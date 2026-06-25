"""
Voice layer — speech<->text via Deepgram, over plain REST.

We call Deepgram's HTTP API directly with httpx (already a transitive dep) rather
than pulling in their SDK: it's a simple request/response API, keeps the
dependency surface small, and matches the project's "feels like any web API"
rationale for choosing Deepgram.

  transcribe(audio_bytes)  -> text         (ASR: Deepgram Nova)
  synthesize(text)         -> audio bytes  (TTS: Deepgram Aura)

The TTS function is written behind a small Protocol so a different provider
(e.g. ElevenLabs for a nicer demo voice) can be swapped in without touching the
endpoint code — only the implementation passed to it changes.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app import config

_DG_LISTEN = "https://api.deepgram.com/v1/listen"
_DG_SPEAK = "https://api.deepgram.com/v1/speak"

# Reasonable network timeout: ASR/TTS on a short clip is quick, but allow slack.
_TIMEOUT = httpx.Timeout(30.0)


class VoiceError(Exception):
    """A voice (ASR/TTS) failure with a user-facing message and HTTP status."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _post(url: str, *, params, headers, **kw) -> httpx.Response:
    """POST to Deepgram, translating transport/HTTP errors into VoiceError."""
    try:
        resp = httpx.post(url, params=params, headers=headers, timeout=_TIMEOUT, **kw)
        resp.raise_for_status()
        return resp
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code in (401, 403):
            raise VoiceError(
                "Deepgram rejected the request — check DEEPGRAM_API_KEY in backend/.env.",
                status_code=502,
            ) from e
        raise VoiceError(f"Deepgram error ({code}).", status_code=502) from e
    except httpx.RequestError as e:
        raise VoiceError(f"Could not reach Deepgram: {e}", status_code=503) from e


def transcribe(audio_bytes: bytes, *, content_type: str = "audio/webm") -> str:
    """
    Speech -> text. Sends the raw audio to Deepgram's pre-recorded endpoint and
    returns the best transcript. `content_type` should match the recording the
    browser produced (the MediaRecorder default is usually audio/webm).
    """
    key = config.require_deepgram_key()
    params = {
        "model": config.ASR_MODEL,
        "smart_format": "true",  # punctuation + capitalization
        "punctuate": "true",
    }
    headers = {"Authorization": f"Token {key}", "Content-Type": content_type}
    resp = _post(_DG_LISTEN, params=params, headers=headers, content=audio_bytes)
    data = resp.json()
    try:
        return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError):
        return ""


class Synthesizer(Protocol):
    """Pluggable TTS: any callable that turns text into audio bytes."""

    def __call__(self, text: str) -> bytes: ...


def synthesize(text: str) -> bytes:
    """
    Text -> speech (MP3 bytes) via Deepgram Aura. Default Synthesizer
    implementation; swap this out for ElevenLabs etc. without changing callers.
    """
    key = config.require_deepgram_key()
    params = {"model": config.TTS_MODEL, "encoding": "mp3"}
    headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
    resp = _post(_DG_SPEAK, params=params, headers=headers, json={"text": text})
    return resp.content
