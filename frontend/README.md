# Frontend — Ask the Book

The React + Vite web client: PDF upload, microphone capture, answer playback, and
the citation panel. It talks to the FastAPI backend over HTTP (`api.js`) and
records audio with the browser's `MediaRecorder` (`useRecorder.js`).

For the full project — including the backend, architecture, and setup — see the
[root README](../README.md).

## Develop

```bash
npm install
npm run dev      # start the dev server (needs the backend running on :8000)
npm run build    # production build
npm run lint     # oxlint
```

The backend must be running for the app to work; see the
[Quickstart](../README.md#quickstart) in the root README.

## Structure

| File | Responsibility |
|---|---|
| `src/App.jsx` | Main component: UI, state, and the ask/answer flow. |
| `src/api.js` | Fetch client for the backend endpoints. |
| `src/useRecorder.js` | `MediaRecorder` hook for microphone capture. |
| `src/App.css` | The "Bold Editorial" theme. |
