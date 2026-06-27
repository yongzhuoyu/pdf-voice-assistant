import { useEffect, useRef, useState } from "react";
import {
  askText, askVoice, checkHealth, getDocument,
  listDocuments, getDocumentStatus, uploadDocument, deleteDocument,
} from "./api";
import { useRecorder } from "./useRecorder";
import "./App.css";

// "Ask the Book" — a spoken/typed Q&A interface over a loaded document.
// Structure: a slim app header (identity + status + loaded document), a focused
// ask area (text + voice), and an answer view with citations as margin notes.

// Generic fallback if a book has no generated questions yet.
const FALLBACK_EXAMPLES = [
  "What is this book about?",
  "Summarize the opening.",
  "What are the main topics?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [backendUp, setBackendUp] = useState(true);
  const [doc, setDoc] = useState(null);        // active document metadata
  const [docs, setDocs] = useState([]);        // all documents (library)
  const [activeId, setActiveId] = useState(null);
  const [uploading, setUploading] = useState(null); // { id, title, progress, stage } while indexing
  const [playing, setPlaying] = useState(false);

  const recorder = useRecorder();
  const audioRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [up, list] = await Promise.all([checkHealth(), listDocuments()]);
      if (cancelled) return;
      setBackendUp(up);
      setDocs(list);
      // Only fetch the active document if the library actually has a ready one —
      // calling /document on an empty library would 409 (no document yet).
      const hasReady = list.some((d) => d.status === "ready");
      if (hasReady) {
        const d = await getDocument();
        if (cancelled) return;
        if (d) {
          setDoc(d);
          setActiveId(d.id || null);
        }
      }
      setLibraryLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Return to the fresh ask state (clears the current answer; keeps the book).
  function resetToHome() {
    stopAudio();
    setResult(null);
    setQuestion("");
    setError("");
    setStatus("");
  }

  // Switch the active book.
  async function selectDocument(id) {
    if (id === activeId) return;
    setResult(null);
    setError("");
    const d = await getDocument(id);
    if (d) {
      setDoc(d);
      setActiveId(id);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Remove this book from the library?")) return;
    try {
      await deleteDocument(id);
      const fresh = await listDocuments();
      setDocs(fresh);
      // Switch to another book, or clear if none remain.
      const next = fresh.find((d) => d.status === "ready");
      if (next) {
        await selectDocument(next.id);
      } else {
        setDoc(null);
        setActiveId(null);
        setResult(null);
      }
    } catch (err) {
      setError(err.message || "Couldn’t remove the book.");
    }
  }

  // Upload a PDF and poll until it's indexed, then switch to it.
  async function handleUpload(file) {
    setError("");
    try {
      const { id, status, duplicate } = await uploadDocument(file);
      if (duplicate || status === "ready") {
        // Same book already in the library — just switch to it, no re-index.
        const fresh = await listDocuments();
        setDocs(fresh);
        await selectDocument(id);
        return;
      }
      setUploading({ id, title: file.name, progress: 0, stage: "queued" });
      pollIndexing(id);
    } catch (err) {
      setError(err.message || "Upload failed.");
    }
  }

  async function pollIndexing(id) {
    try {
      const rec = await getDocumentStatus(id);
      if (rec.status === "ready") {
        setUploading(null);
        const fresh = await listDocuments();
        setDocs(fresh);
        await selectDocument(id);
      } else if (rec.status === "failed") {
        setUploading(null);
        setError(`Couldn’t prepare that book: ${rec.error || "please try another PDF"}`);
      } else {
        setUploading({ id, title: rec.title, progress: rec.progress, stage: rec.stage });
        setTimeout(() => pollIndexing(id), 1500);
      }
    } catch {
      setTimeout(() => pollIndexing(id), 3000);
    }
  }

  async function ask(q) {
    const query = (q ?? question).trim();
    if (!query || loading) return;
    setQuestion(query);
    await run(async () => {
      const data = await askText(query, activeId);
      return { ...data, transcript: null, audio_base64: null };
    });
  }

  async function toggleRecording() {
    if (loading) return;
    if (!recorder.recording) {
      setError("");
      setResult(null);
      await recorder.start();
      return;
    }
    const blob = await recorder.stop();
    if (!blob) return;
    await run(async () => {
      setStatus("Transcribing and answering…");
      return askVoice(blob, activeId);
    });
  }

  async function run(work) {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await work();
      setResult(data);
      if (data.audio_base64) playAnswer(data.audio_base64, data.audio_mime);
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
      setStatus("");
    }
  }

  function playAnswer(b64, mime = "audio/mpeg") {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.play().then(() => setPlaying(true)).catch(() => {});
    }
  }
  function stopAudio() {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setPlaying(false);
  }
  function replayAudio() {
    if (audioRef.current?.src) {
      audioRef.current.currentTime = 0;
      audioRef.current.play().then(() => setPlaying(true)).catch(() => {});
    }
  }

  const showEmpty = !result && !error && !loading && !recorder.recording;
  // No book in the library and none indexing: prompt the user to add one.
  // Keyed on the documents list (the reliable signal), not on /document.
  const [libraryLoaded, setLibraryLoaded] = useState(false);
  const noLibrary =
    backendUp && libraryLoaded && docs.length === 0 && !uploading;

  return (
    <div className="app">
      <AppHeader
        doc={doc}
        docs={docs}
        activeId={activeId}
        onSelect={selectDocument}
        onUpload={handleUpload}
        onDelete={handleDelete}
        onHome={resetToHome}
        canReset={Boolean(result || error)}
        uploading={uploading}
      />

      <main className="main">
        {!backendUp && (
          <p className="notice error">
            Can’t reach the server. Start the backend on port 8000, then reload.
          </p>
        )}

        {uploading && <IndexingBanner uploading={uploading} />}

        {noLibrary && (
          <section className="empty-library">
            <h2 className="empty-title">No book loaded yet</h2>
            <p className="empty-text">
              Add a PDF to get started, then ask questions about it by voice
              or text and hear the answers read back.
            </p>
            <button className="ask-btn" onClick={() => document.getElementById("hidden-upload")?.click()}>
              + Add a book
            </button>
          </section>
        )}

        {!noLibrary && (
        <section className="ask-area">
          <h2 className="ask-prompt">
            Ask a question{doc?.title ? <> about <em>{doc.title}</em></> : ""}.
          </h2>

          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
          >
            <input
              className="ask-input"
              type="text"
              value={question}
              placeholder="Type your question, or use the microphone…"
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading || recorder.recording}
              autoFocus
            />
            <MicButton
              recording={recorder.recording}
              level={recorder.level}
              disabled={loading}
              onClick={toggleRecording}
            />
            <button
              className="ask-btn"
              type="submit"
              disabled={loading || recorder.recording || !question.trim()}
            >
              {loading ? "Reading…" : "Ask"}
            </button>
          </form>

          {recorder.recording && (
            <p className="status-line live">● Listening — click the microphone to finish.</p>
          )}
          {status && !recorder.recording && <p className="status-line">{status}</p>}
        </section>
        )}

        {(error || recorder.error) && (
          <p className="notice error">{error || recorder.error}</p>
        )}

        {!noLibrary && showEmpty && (
          <Examples
            examples={doc?.questions?.length ? doc.questions : FALLBACK_EXAMPLES}
            onPick={(q) => ask(q)}
          />
        )}

        {result && (
          <Answer
            result={result}
            playing={playing}
            onStop={stopAudio}
            onReplay={replayAudio}
            hasAudio={Boolean(result.audio_base64)}
          />
        )}
      </main>

      <audio ref={audioRef} hidden onEnded={() => setPlaying(false)} />
    </div>
  );
}

function AppHeader({ doc, docs, activeId, onSelect, onUpload, onDelete, onHome, canReset, uploading }) {
  const fileRef = useRef(null);

  function pickFile(e) {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = ""; // allow re-uploading the same filename
  }

  const readyDocs = docs.filter((d) => d.status === "ready");

  return (
    <header className="appbar">
      <button
        type="button"
        className={`appbar-left brand-home${canReset ? " resettable" : ""}`}
        onClick={onHome}
        title={canReset ? "Start a new question" : "Ask the Book"}
        aria-label="Ask the Book — start a new question"
      >
        <span className="brand">Ask the Book</span>
        <span className="brand-sub">a spoken reading companion</span>
      </button>

      <div className="appbar-right">
        {readyDocs.length > 1 && (
          <select
            className="doc-select"
            value={activeId || ""}
            onChange={(e) => onSelect(e.target.value)}
            title="Switch book"
          >
            {readyDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
        )}

        {doc && (
          <span className="doc-meta">
            {doc.n_chapters} chapters · {doc.n_pages} pages
          </span>
        )}

        {doc && activeId && (
          <button
            className="remove-btn"
            onClick={() => onDelete(activeId)}
            title="Remove this book"
          >
            Remove
          </button>
        )}

        {doc && <span className="appbar-divider" aria-hidden="true" />}

        <button
          className="upload-btn"
          onClick={() => fileRef.current?.click()}
          disabled={Boolean(uploading)}
          title="Add a PDF book"
        >
          {uploading ? "Preparing…" : "+ Add book"}
        </button>
        <input
          id="hidden-upload"
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={pickFile}
        />
      </div>
    </header>
  );
}

function IndexingBanner({ uploading }) {
  const pct = Math.round((uploading.progress || 0) * 100);
  return (
    <div className="indexing">
      <div className="indexing-head">
        <span className="indexing-title">Preparing “{uploading.title}”</span>
        <span className="indexing-pct">{pct}%</span>
      </div>
      <div className="indexing-bar">
        <div className="indexing-fill" style={{ width: `${pct}%` }} />
      </div>
      <p className="indexing-stage">
        {uploading.stage} — this can take several minutes for a full-length book.
      </p>
    </div>
  );
}

function MicButton({ recording, level, disabled, onClick }) {
  const scale = recording ? 1 + level * 0.5 : 1;
  return (
    <button
      type="button"
      className={`mic ${recording ? "mic-on" : ""}`}
      onClick={onClick}
      disabled={disabled}
      title={recording ? "Stop recording" : "Ask by voice"}
      aria-label={recording ? "Stop recording" : "Ask by voice"}
    >
      <span className="mic-ring" style={{ transform: `scale(${scale})` }} />
      <MicGlyph stop={recording} />
    </button>
  );
}

function MicGlyph({ stop }) {
  if (stop) return <span className="mic-glyph">■</span>;
  return (
    <svg className="mic-svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"
      />
    </svg>
  );
}

function Examples({ examples, onPick }) {
  return (
    <section className="examples">
      <p className="examples-head">Try asking</p>
      <ul className="example-list">
        {examples.map((q, i) => (
          <li key={i}>
            <button className="example" onClick={() => onPick(q)}>
              {q}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Answer({ result, playing, onStop, onReplay, hasAudio }) {
  const { answer, out_of_scope, citations, transcript } = result;

  const seen = new Set();
  const uniqueCitations = (citations || []).filter((c) => {
    const key = `${c.chapter_number}-${c.start_page}-${c.end_page}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <article className="answer">
      <div className="answer-body">
        {transcript && (
          <p className="transcript">
            <span className="transcript-label">You asked</span>“{transcript}”
          </p>
        )}
        {out_of_scope && <p className="oos-flag">Not covered in the book</p>}
        <div className={out_of_scope ? "prose no-dropcap" : "prose"}>
          {answer.split(/\n\n+/).map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>

        {hasAudio && (
          <div className="audio-bar">
            {playing ? (
              <button className="audio-btn" onClick={onStop}>■ Stop</button>
            ) : (
              <button className="audio-btn" onClick={onReplay}>▶ Replay answer</button>
            )}
          </div>
        )}
      </div>

      <aside className="margin">
        <p className="margin-head">
          Sources{uniqueCitations.length ? ` (${uniqueCitations.length})` : ""}
        </p>
        {uniqueCitations.length > 0 ? (
          <ol className="margin-notes">
            {uniqueCitations.map((c, i) => (
              <li key={i} className="margin-note">
                <span className="cite-num">{i + 1}</span>
                <div className="cite-body">
                  <p className="cite-head">
                    <span className="cite-loc">
                      Ch. {c.chapter_number} · {pageLabel(c.start_page, c.end_page)}
                    </span>
                    <span className="cite-title">{c.chapter_title}</span>
                  </p>
                  {c.quoted_text && (
                    <p className="cite-quote">“{trim(c.quoted_text)}”</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="margin-empty">No passages cited.</p>
        )}
      </aside>
    </article>
  );
}

// "P. 3" for a single page, "PP. 3–5" for a range.
function pageLabel(start, end) {
  return start === end ? `P. ${start}` : `PP. ${start}–${end}`;
}

// Show the quote in full when it's short; otherwise truncate cleanly at a word
// boundary (never mid-word) with a tidy ellipsis.
function trim(s, n = 220) {
  s = s.replace(/\s+/g, " ").trim();
  if (s.length <= n) return s;
  const cut = s.slice(0, n);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 0 ? cut.slice(0, lastSpace) : cut).replace(/[.,;:]$/, "") + "…";
}
