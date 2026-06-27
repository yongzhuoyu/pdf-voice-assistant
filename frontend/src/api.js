// Thin client for the backend. Keeps all fetch/URL logic in one place so
// components just call askText() / askVoice() and get clean data back.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const UNREACHABLE =
  "Can’t reach the server. Make sure the backend is running on port 8000.";

/** Text question -> { answer, out_of_scope, citations }. */
export async function askText(question, docId) {
  const res = await postJSON(`${BASE}/ask`, { question, doc_id: docId || null });
  return res.json();
}

/**
 * Spoken question (audio Blob) -> { transcript, answer, out_of_scope,
 * citations, audio_base64, audio_mime }.
 */
export async function askVoice(audioBlob, docId) {
  const form = new FormData();
  form.append("audio", audioBlob, "question.webm");
  if (docId) form.append("doc_id", docId);
  const res = await send(`${BASE}/voice`, { method: "POST", body: form });
  return res.json();
}

/** Is the backend reachable? Returns boolean, never throws. */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    if (!res.ok) return false;
    const data = await res.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

/** Metadata for one document (or the default): { id, title, n_chapters, n_pages }, or null. */
export async function getDocument(docId) {
  try {
    const url = docId ? `${BASE}/document?doc_id=${encodeURIComponent(docId)}` : `${BASE}/document`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    return data && data.id ? data : null;  // {id: null} means no document loaded
  } catch {
    return null;
  }
}

/** List all books and their indexing status. [] on failure. */
export async function listDocuments() {
  try {
    const res = await fetch(`${BASE}/documents`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

/** One document's status/progress record. */
export async function getDocumentStatus(docId) {
  const res = await fetch(`${BASE}/documents/${encodeURIComponent(docId)}`);
  if (!res.ok) throw new Error("status check failed");
  return res.json();
}

/** Upload a PDF; returns { id, status, duplicate? }. Indexing runs in the background. */
export async function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await send(`${BASE}/documents`, { method: "POST", body: form });
  return res.json();
}

/** Remove a book from the library. */
export async function deleteDocument(docId) {
  const res = await send(`${BASE}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
  return res.json();
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
