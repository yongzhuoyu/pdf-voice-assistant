// Thin client for the backend. Keeps all fetch/URL logic in one place so
// components just call askText() / askVoice() and get clean data back.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const UNREACHABLE =
  "Can’t reach the server. Make sure the backend is running on port 8000.";

/** Text question -> { answer, out_of_scope, citations }. */
export async function askText(question) {
  const res = await postJSON(`${BASE}/ask`, { question });
  return res.json();
}

/**
 * Spoken question (audio Blob) -> { transcript, answer, out_of_scope,
 * citations, audio_base64, audio_mime }.
 */
export async function askVoice(audioBlob) {
  const form = new FormData();
  form.append("audio", audioBlob, "question.webm");
  const res = await send(`${BASE}/voice`, { method: "POST", body: form });
  return res.json();
}

/** Is the backend up and the index loaded? Returns boolean, never throws. */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    if (!res.ok) return false;
    const data = await res.json();
    return Boolean(data.index_loaded);
  } catch {
    return false;
  }
}

/** Loaded-document metadata: { title, chapters, n_chapters, n_pages }. null on failure. */
export async function getDocument() {
  try {
    const res = await fetch(`${BASE}/document`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// --- internals ---

async function postJSON(url, body) {
  return send(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function send(url, opts) {
  let res;
  try {
    res = await fetch(url, opts);
  } catch {
    // Network-level failure (server down, CORS, DNS) — fetch rejects.
    throw new Error(UNREACHABLE);
  }
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res;
}

async function safeDetail(res) {
  try {
    const data = await res.json();
    return data.detail;
  } catch {
    return null;
  }
}
