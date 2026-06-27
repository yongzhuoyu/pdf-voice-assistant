import { useEffect, useRef, useState } from "react";
import { askText, askVoice, checkHealth, getDocument } from "./api";
import { useRecorder } from "./useRecorder";
import "./App.css";

// "Ask the Book" — a spoken/typed Q&A interface over a loaded document.
// Structure: a slim app header (identity + status + loaded document), a focused
// ask area (text + voice), and an answer view with citations as margin notes.

const EXAMPLES = [
  "How did Holmes deduce that Watson had been out in the rain?",
  "What was unusual about the Red-Headed League?",
  "Why did the King of Bohemia want the photograph back?",
  "What did Holmes notice about Mary Sutherland’s appearance?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [backendUp, setBackendUp] = useState(true);
  const [doc, setDoc] = useState(null);        // { title, chapters, n_chapters, n_pages }
  const [playing, setPlaying] = useState(false);

  const recorder = useRecorder();
  const audioRef = useRef(null);

  useEffect(() => {
    checkHealth().then((up) => {
      setBackendUp(up);
      if (up) getDocument().then(setDoc);
    });
  }, []);

  async function ask(q) {
    const query = (q ?? question).trim();
    if (!query || loading) return;
    setQuestion(query);
    await run(async () => {
      const data = await askText(query);
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
      return askVoice(blob);
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

  return (
    <div className="app">
      <AppHeader doc={doc} backendUp={backendUp} />

      <main className="main">
        {!backendUp && (
          <p className="notice error">
            Can’t reach the server. Start the backend on port 8000, then reload.
          </p>
        )}

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

        {(error || recorder.error) && (
          <p className="notice error">{error || recorder.error}</p>
        )}

        {showEmpty && <Examples examples={EXAMPLES} onPick={(q) => ask(q)} />}

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

function AppHeader({ doc, backendUp }) {
  return (
    <header className="appbar">
      <div className="appbar-left">
        <span className="brand">Ask the Book</span>
        <span className="brand-sub">a spoken reading companion</span>
      </div>
      <div className="appbar-right">
        {doc && (
          <span className="doc-meta">
            {doc.n_chapters} chapters · {doc.n_pages} pages
          </span>
        )}
        <span className={`statusdot ${backendUp ? "ok" : "down"}`} />
        <span className="status-label">{backendUp ? "Index ready" : "Offline"}</span>
      </div>
    </header>
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
      <p className="examples-foot">
        Answers are drawn only from the book. If it isn’t covered, you’ll be told
        so rather than given a guess.
      </p>
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
                <span className="cite-loc">
                  Ch. {c.chapter_number} · pp. {c.start_page}–{c.end_page}
                </span>
                <span className="cite-title">{c.chapter_title}</span>
                {c.quoted_text && (
                  <span className="cite-quote">“{trim(c.quoted_text)}”</span>
                )}
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

function trim(s, n = 120) {
  s = s.replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
}
