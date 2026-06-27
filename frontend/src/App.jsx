import { useEffect, useRef, useState } from "react";
import { askText, askVoice, checkHealth } from "./api";
import { useRecorder } from "./useRecorder";
import "./App.css";

// Day 3: text + voice Q&A. Type or speak a question; get a grounded answer with
// citations rendered as margin notes, and (for voice) hear it read back.

export default function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);   // { transcript?, answer, out_of_scope, citations, audio? }
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");      // transient status line (e.g. "Transcribing…")
  const [error, setError] = useState("");
  const [backendUp, setBackendUp] = useState(true);
  const [playing, setPlaying] = useState(false);

  const recorder = useRecorder();
  const audioRef = useRef(null);

  // Check the backend on load so we can warn early if it's down.
  useEffect(() => {
    checkHealth().then(setBackendUp);
  }, []);

  async function submitText(e) {
    e?.preventDefault();
    const q = question.trim();
    if (!q || loading) return;
    await run(async () => {
      const data = await askText(q);
      return { ...data, transcript: null, audio: null };
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
    // Stop -> get the audio -> send to /voice.
    const blob = await recorder.stop();
    if (!blob) return;
    await run(async () => {
      setStatus("Transcribing and answering…");
      const data = await askVoice(blob);
      return data;
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
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setPlaying(false);
  }

  function replayAudio() {
    if (audioRef.current?.src) {
      audioRef.current.currentTime = 0;
      audioRef.current.play().then(() => setPlaying(true)).catch(() => {});
    }
  }

  const micError = recorder.error;

  return (
    <div className="page">
      <header className="masthead">
        <p className="kicker">A spoken reading companion</p>
        <h1 className="title">Ask the Book</h1>
        <p className="subtitle">
          The Adventures of Sherlock Holmes — speak or type a question, and hear
          an answer drawn from the text, with the page it came from.
        </p>
      </header>

      <main className="reading">
        {!backendUp && (
          <p className="notice error">
            Can’t reach the server. Start the backend on port 8000, then reload.
          </p>
        )}

        <div className="ask-zone">
          <MicButton
            recording={recorder.recording}
            level={recorder.level}
            disabled={loading}
            onClick={toggleRecording}
          />

          <form className="ask" onSubmit={submitText}>
            <input
              className="ask-input"
              type="text"
              value={question}
              placeholder="…or type: How did Holmes deduce that Watson had been out in the rain?"
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading || recorder.recording}
            />
            <button
              className="ask-btn"
              type="submit"
              disabled={loading || recorder.recording || !question.trim()}
            >
              {loading ? "Reading…" : "Ask"}
            </button>
          </form>
        </div>

        {(status || recorder.recording) && (
          <p className="notice status">
            {recorder.recording ? "Listening… click the mic to finish." : status}
          </p>
        )}
        {(error || micError) && <p className="notice error">{error || micError}</p>}

        {result && (
          <Answer
            result={result}
            playing={playing}
            onStop={stopAudio}
            onReplay={replayAudio}
            hasAudio={Boolean(result.audio_base64)}
          />
        )}

        {!result && !error && !loading && !recorder.recording && (
          <p className="hint">
            Ask anything about the twelve stories. If the book doesn’t cover it,
            it will say so rather than guess.
          </p>
        )}
      </main>

      <audio ref={audioRef} hidden onEnded={() => setPlaying(false)} />

      <footer className="colophon">
        Grounded retrieval over the full text — hybrid search, reranking, and
        Claude with native citations.
      </footer>
    </div>
  );
}

function MicButton({ recording, level, disabled, onClick }) {
  // Scale the pulse ring with the live mic level while recording.
  const scale = recording ? 1 + level * 0.6 : 1;
  return (
    <button
      type="button"
      className={`mic ${recording ? "mic-on" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={recording ? "Stop recording" : "Ask by voice"}
    >
      <span className="mic-ring" style={{ transform: `scale(${scale})` }} />
      <span className="mic-glyph">{recording ? "■" : "●"}</span>
    </button>
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
            <span className="transcript-label">You asked</span>
            “{transcript}”
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
              <button className="audio-btn" onClick={onStop}>
                ■ Stop
              </button>
            ) : (
              <button className="audio-btn" onClick={onReplay}>
                ▶ Replay answer
              </button>
            )}
          </div>
        )}
      </div>

      {uniqueCitations.length > 0 && (
        <aside className="margin">
          <p className="margin-head">Sources</p>
          <ol className="margin-notes">
            {uniqueCitations.map((c, i) => (
              <li key={i} className="margin-note">
                <span className="cite-loc">
                  Ch. {c.chapter_number} · pp. {c.start_page}–{c.end_page}
                </span>
                <span className="cite-title">{toTitleCase(c.chapter_title)}</span>
                {c.quoted_text && (
                  <span className="cite-quote">“{trim(c.quoted_text)}”</span>
                )}
              </li>
            ))}
          </ol>
        </aside>
      )}
    </article>
  );
}

function trim(s, n = 120) {
  s = s.replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function toTitleCase(s) {
  return s.toLowerCase().replace(/\b\w/g, (m) => m.toUpperCase());
}
