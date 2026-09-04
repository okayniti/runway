# Deployment

Backend (FastAPI) to Railway or Render, frontend (Next.js) to Vercel. Deploy the backend first — the frontend build needs its URL.

## 1. Backend — Railway or Render

Both platforms auto-detect a Python app from `requirements.txt` and will run the `Procfile` in the repo root (`web: uvicorn api.app:app --host 0.0.0.0 --port $PORT`) without you typing a start command by hand. If a platform doesn't pick up the `Procfile` on its own, set the start command to that same line explicitly in its dashboard.

**Persistent storage — do this before your first deploy, not after.** SQLite writes to a container's own filesystem vanish on every redeploy unless that path is on a persistent volume. Railway and Render both offer one, but you choose the mount path yourself:

- **Railway**: Project → your service → **Volumes** → attach a volume, mount path e.g. `/data`.
- **Render**: your service → **Disks** → add a disk, mount path e.g. `/var/data`.

Whichever path you pick, set:
```
RUNWAY_DB_PATH=/data/store.db          # or wherever you mounted it
```
If you skip this, the app still runs fine — it just starts a fresh, empty history store on every redeploy, silently. `/health` and `/forecast` both work either way; only the `/stats` and `/calibration` track record is at stake.

**Environment variables to set** (Railway: service → Variables; Render: service → Environment):

| Variable | Required | Value |
|---|---|---|
| `RUNWAY_DB_PATH` | recommended | path on your mounted volume, e.g. `/data/store.db` |
| `RUNWAY_WEBHOOK_URL` | optional | your Slack Incoming Webhook URL, if you want alerts |
| `RUNWAY_API_KEYS` | optional | JSON map of real API keys, e.g. `{"prod-key": "acme-corp"}` — defaults to a demo key otherwise |
| `RUNWAY_CORS_ORIGINS` | do this after step 2 | your Vercel URL, e.g. `https://runway-demo.vercel.app` — leave unset for now |
| `PORT` | don't set this | Railway/Render inject it themselves |

Neither platform needs a build command beyond the default `pip install -r requirements.txt` they auto-detect. The model checkpoint (`model/checkpoints/bilstm_cashflow.pt`) is committed to the repo — see item 6 below — so there's no training step on deploy.

Once it's live, confirm before moving on:
```bash
curl https://<your-backend-url>/health
# {"status":"ok"}
```
If you get `{"status":"unhealthy", ...}`, the checkpoint didn't load — check the deploy log for the actual error rather than guessing.

## 2. Frontend — Vercel

Import the repo, set the project's **Root Directory** to `frontend` (this is a monorepo — Vercel won't find `package.json` at the repo root). Build command and output directory are Next.js defaults; nothing to change there.

**Environment variable** (Vercel: project → Settings → Environment Variables):

| Variable | Required | Value |
|---|---|---|
| `BACKEND_URL` | yes | your backend's URL from step 1, e.g. `https://runway-api.up.railway.app` — no trailing slash |

This is deliberately not `NEXT_PUBLIC_BACKEND_URL` or similar — it's read server-side only, inside `next.config.ts`'s rewrite proxy, and is never sent to the browser. The frontend's own client-side code always calls the same-origin `/api/backend/*` path, never the backend URL directly (see the comment at the top of `frontend/next.config.ts`). That's also why the backend needs no CORS entry for the frontend at all — proxied requests are server-to-server, and a browser's CORS policy doesn't apply to those.

Deploy, then confirm:
```bash
curl https://<your-vercel-url>/api/backend/health
# {"status":"ok"}
```
If this fails but the backend's own `/health` (step 1) works, `BACKEND_URL` is wrong or wasn't set before the build ran — Vercel bakes it in at build time, so a var added after the fact needs a redeploy, not just a page refresh.

## 3. Close the loop: CORS

Now that Vercel has assigned a URL, go back to the backend's env vars and set:
```
RUNWAY_CORS_ORIGINS=https://<your-vercel-url>
```
This isn't needed for the frontend itself (see above — it's a same-origin proxy, not a cross-origin browser call). It only matters if something else calls the backend's URL directly from a browser — a second frontend, someone hitting `/docs` from a different origin's JS, that kind of thing. Leave it empty and the API still works fine for the deployed frontend; you're only opening a door you might not need. Redeploy the backend after setting it — this is read once at process start, not per-request.

## Everything else that matters before you deploy

**The model checkpoint is already committed.** `model/checkpoints/bilstm_cashflow.pt` is ~23KB (4,350 parameters) — small enough that committing it outright made more sense than adding a training step to every deploy. `.gitignore` was updated to exempt this one file from the general checkpoint-artifact exclusion; everything else under `checkpoints/` still gets ignored. If you retrain with different data or architecture, re-run `python model/train.py` locally and commit the new checkpoint the same way — there's no separate deploy-time training path, and you shouldn't need one for a model this size.

**The Slack webhook.** Without `RUNWAY_WEBHOOK_URL` set, the app runs fine and simply never fires an alert — this isn't a required variable, just one you'll want before demoing the alerting path.

**API keys.** The built-in default (`{"demo-key": "demo-tenant"}`) exists so the app runs with zero config. Replace it with `RUNWAY_API_KEYS` before pointing this at anything that isn't a demo — the default key is sitting in this repo's git history.

**The Streamlit dashboard (`dashboard/`) isn't part of this deployment.** It's a separate local dev tool that takes an API base URL as a text input at runtime; deploy it separately (e.g. Streamlit Community Cloud) if you want it public, pointed at the same backend URL from step 1.

## Decisions that are yours, not mine

- **Railway vs. Render** — pick one; the steps above work for either. Render has historically been a little more explicit about wanting a start command typed into its dashboard rather than always auto-reading a `Procfile`; if it doesn't pick the `Procfile` up, paste that same line in as the start command.
- **Where the persistent volume mounts** — `/data` and `/var/data` above are just conventions from each platform's own docs, not requirements. Whatever path you choose, `RUNWAY_DB_PATH` needs to point inside it.
- **Whether to set `RUNWAY_CORS_ORIGINS` at all** — the deployed frontend doesn't need it. Only set it if you know something else will call the backend directly from a browser.
