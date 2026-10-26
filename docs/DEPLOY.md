# Deployment

GridBrick runs as two services with one public domain:

- `web` — React/Vite static build, served by the Vercel CDN.
- `api` — the FastAPI application, mounted at `/api`.

The same repository also runs as two Docker containers. Both paths were exercised locally.

---

## Option A — Vercel Services (primary)

`vercel.json` declares both services and routes `/api/*` to FastAPI while everything else goes to the Vite build. Vercel's service routing preserves the original request path, so the FastAPI routes stay `/api/v1/...` with no prefix hacks.

### Permanent deployment

```bash
npm install -g vercel        # or use npx
vercel login
vercel --prod
```

The project uses:

- Frontend root: `frontend/`
- Frontend framework: Vite
- Frontend output: `dist`
- Backend root: `backend/`
- Backend entrypoint: `app.main:app` (FastAPI, Python 3.13)
- Backend dependencies: `backend/pyproject.toml` + `backend/uv.lock`
- Function duration: 60 s, memory: 1024 MB

Vercel detects the same settings from `vercel.json`; no dashboard build overrides are required.

### Anonymous temporary deployment

Without an account:

```bash
npx vercel deploy --temporary --yes
```

The CLI prints a temporary URL and a claim URL. **Anonymous deployments sit behind Vercel's claim wall: the URL returns 403 until claimed.** Open the claim URL, sign in (or create a free account), and transfer the project. It then stops expiring and the URL becomes public.

A temporary deployment created during development:

- Claim: <https://vercel.com/claim-deployment?code=18b52160-c2e4-45a4-abda-058908527791>
- URL: <https://flying-cygnus-lf7tsdl.tmp.now>
- Expiry: 56 minutes after creation. If it has expired, rerun the command above.

After claiming, replace this section and the live link in `README.md` with the permanent production URL.

### Backend behaviour on Vercel

- The filesystem is read-only except `/tmp`. `backend/app/config.py` switches the SQLite path to `/tmp/gridbrick.db` when the `VERCEL` environment variable is present.
- The FastAPI lifespan runs on cold start: it creates the schema and loads the committed seed. A cold start therefore does not depend on BMRS being reachable.
- The seed is deterministic. Every instance reconstructs the same warehouse, so API responses are reproducible.
- `/tmp` is not durable and is not shared across all instances. This is acceptable for a read-only demo; it is not a production database.
- The accuracy endpoint takes several seconds on a cold instance because it builds the walk-forward report. `maxDuration` is 60 s.

### Vercel checklist

1. Open `/` — Decision Desk loads.
2. Open `/api/v1/health` — `status: ok`, 2,113 actuals, 25,696 forecast points, 352 vintages.
3. Open `/#/accuracy?d=2026-01-14` — raw and calibrated scorecards render.
4. Open `/#/procurement?d=2026-01-14` — plan renders and changes when the cost ratio changes.
5. Open `/docs` — FastAPI OpenAPI page loads through the API service.
6. Check a direct deep link such as `/#/method?d=2026-01-31`.

---

## Option B — Docker Compose (local / self-hosted)

```bash
docker compose up --build
```

| Service | Port | Notes |
|---|---:|---|
| `frontend` | `8088` | nginx; proxies `/api` to `backend:8000` |
| `backend` | internal `8000` | uvicorn, non-root user, health check |

The backend mounts a named volume at `/app/data` for SQLite. The frontend waits for the backend health check before starting.

To rebuild after code changes:

```bash
docker compose up --build -d
docker compose logs -f backend
```

Stop and remove the warehouse volume:

```bash
docker compose down -v
```

---

## Option C — Render / Railway / Fly.io

The backend is a standard container listening on `$PORT`:

```bash
docker build -t gridbrick-api ./backend
docker run -p 8000:8000 \
  -e GRIDBRICK_ENVIRONMENT=production \
  -e GRIDBRICK_DATABASE_URL=sqlite:////tmp/gridbrick.db \
  gridbrick-api
```

For a managed container host:

1. Point the service at `backend/Dockerfile`.
2. Set `GRIDBRICK_DATABASE_URL=sqlite:////tmp/gridbrick.db` unless you attach a persistent disk. If you attach a disk, mount it at `/app/data` and use `sqlite:////app/data/gridbrick.db`.
3. Set `GRIDBRICK_CORS_ORIGINS` to the public frontend origin.
4. Health check path: `/api/v1/health`.
5. Deploy the frontend with `VITE_API_BASE_URL=https://your-api.example.com` so the browser calls the API directly. `frontend/Dockerfile` bakes this variable at build time.

The seed loads automatically on first boot; no database provisioning is needed.

---

## Option D — Heroku (backend container + static frontend)

Heroku is not the primary path because it requires a separate frontend host, but the backend image is Heroku-compatible: the CMD expands `${PORT:-8000}`.

```bash
heroku create gridbrick-api-<suffix>
heroku container:login
docker build -t registry.heroku.com/<app>/web ./backend
docker push registry.heroku.com/<app>/web
heroku container:release web -a <app>
heroku config:set -a <app> \
  GRIDBRICK_ENVIRONMENT=production \
  GRIDBRICK_DATABASE_URL=sqlite:////tmp/gridbrick.db
```

Then build the frontend against the Heroku URL and host `frontend/dist` on any static host:

```bash
cd frontend
$env:VITE_API_BASE_URL = "https://<app>.herokuapp.com"   # PowerShell
npm ci
npm run build
```

Set `GRIDBRICK_CORS_ORIGINS` to the static site's origin. Do not use the nginx container on Heroku: its `proxy_pass http://backend:8000` assumes Docker Compose DNS.

---

## Environment variables

| Variable | Production recommendation |
|---|---|
| `GRIDBRICK_ENVIRONMENT` | `production` |
| `GRIDBRICK_DATABASE_URL` | `sqlite:////tmp/gridbrick.db` on serverless/ephemeral hosts; a mounted disk otherwise |
| `GRIDBRICK_SEED_DIR` | Leave unset in the container images (defaults to the image's `seeds/`) |
| `GRIDBRICK_CORS_ORIGINS` | Comma-separated public frontend origin(s) |
| `GRIDBRICK_ADMIN_TOKEN` | Set a long random value if exposing `/admin/ingest` |
| `GRIDBRICK_ALLOW_LIVE_INGEST` | `false` for a fully offline demo |
| `GRIDBRICK_DEFAULT_CUTOFF_HOUR` | `9` |
| `GRIDBRICK_DEFAULT_CUTOFF_MINUTE` | `30` |

Vercel sets `VERCEL=1` automatically; the app uses this to select `/tmp` and `environment=production`.

---

## Troubleshooting

**The temporary Vercel URL returns 403.** This is expected until the anonymous deployment is claimed. Use the claim URL printed by the CLI.

**The API returns 500 on Vercel after a cold start.** Check the function logs. The usual cause is a missing seed file in the bundle or a read-only SQLite path. Confirm `backend/seeds/` is present and `GRIDBRICK_DATABASE_URL` points at `/tmp`.

**Local backend port is already in use.** This workspace had an unrelated service on 8000; use `--port 8010` and set `VITE_PROXY_TARGET=http://localhost:8010`.

**`docker compose up` fails to bind 8080.** Another service owns 8080. Change the host side of the `frontend` port mapping in `docker-compose.yml`; 8088 is used here.

**Accuracy takes 5–9 seconds.** That is the full walk-forward report over 744 hours. The frontend caches it by `(start, end, cutoff)`; subsequent views are instant.

**Seed counts differ.** Run `GET /api/v1/health`. The committed snapshot is 2,113 actual half-hours, 25,696 forecast points, 352 vintages. A live ingestion will add rows.
