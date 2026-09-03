# runway — frontend

The Next.js demo site: a live forecast panel that runs real transaction
data against the backend API, a track-record section and calibration
spotlight backed by real `/stats` and `/calibration` data, and the rest
of the page copy. No forecasting logic lives here — see the repo root
README for the full system.

## Setup

The backend API must be running first (see the [root README](../README.md)'s
Setup section). Then:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Requests to
`/api/backend/*` are proxied server-side to the backend (defaults to
`http://127.0.0.1:8000`; override with the `BACKEND_URL` env var) — see
`next.config.ts`.
