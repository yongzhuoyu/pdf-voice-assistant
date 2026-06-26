import { useCallback, useRef, useState } from "react";

// Encapsulates browser microphone recording via MediaRecorder. Keeps all the
// getUserMedia / chunk-collection plumbing out of the component, exposing a
// simple start/stop interface plus a live audio level for the waveform.
//
//   const rec = useRecorder();
//   rec.start();                  -> begins recording (asks mic permission)
//   const blob = await rec.stop(); -> resolves with the recorded audio Blob
//   rec.recording, rec.level, rec.error

export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);     // 0..1 live mic amplitude
  const [error, setError] = useState("");

  const mediaRef = useRef(null);             // MediaRecorder
  const chunksRef = useRef([]);              // collected audio chunks
  const streamRef = useRef(null);            // the mic MediaStream
  const stopResolveRef = useRef(null);       // resolve fn for the stop() promise
  const rafRef = useRef(null);               // requestAnimationFrame id
  const audioCtxRef = useRef(null);

  const start = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const mr = new MediaRecorder(stream);
      mediaRef.current = mr;
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: mr.mimeType || "audio/webm",
        });
        cleanup();
        stopResolveRef.current?.(blob);
      };
      mr.start();
      setRecording(true);
      meter(stream);
    } catch (err) {
      setError(
        err?.name === "NotAllowedError"
          ? "Microphone permission denied."
          : "Could not access the microphone."
      );
    }
  }, []);

  const stop = useCallback(() => {
    return new Promise((resolve) => {
      const mr = mediaRef.current;
      if (!mr || mr.state === "inactive") {
        resolve(null);
        return;
      }
      stopResolveRef.current = resolve;
      mr.stop();
      setRecording(false);
    });
  }, []);

  // Live amplitude meter for the recording waveform.
  function meter(stream) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtxRef.current = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      // RMS amplitude around the 128 midpoint, scaled to ~0..1.
      let sum = 0;
      for (const v of data) sum += (v - 128) ** 2;
      const rms = Math.sqrt(sum / data.length) / 128;
      setLevel(Math.min(1, rms * 3));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  }

  function cleanup() {
    cancelAnimationFrame(rafRef.current);
    setLevel(0);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }

  return { recording, level, error, start, stop };
}
