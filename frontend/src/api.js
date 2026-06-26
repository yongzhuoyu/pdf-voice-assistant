// Thin client for the backend. Keeps all fetch/URL logic in one place so
// components just call askText() / askVoice() and get clean data back.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

/** Text question -> { answer, out_of_scope, citations }. */
export async function askText(question) {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

/**
 * Spoken question (audio Blob) -> { transcript, answer, out_of_scope,
 * citations, audio_base64, audio_mime }.
 */
export async function askVoice(audioBlob) {
  const form = new FormData();
  form.append("audio", audioBlob, "question.webm");
  const res = await fetch(`${BASE}/voice`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail || `Voice request failed (${res.status})`);
  }
  return res.json();
}

async function safeDetail(res) {
  try {
    const data = await res.json();
    return data.detail;
  } catch {
    return null;
  }
}
