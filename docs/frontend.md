# Frontend development

The results explorer lives under `frontend/` and uses React, Vite, TypeScript,
and Tailwind CSS v4. It talks only to the FastAPI routes documented in
`docs/api.md`. There are no sample runs or browser-side fixture data.

## Install

From the repository root:

```bash
cd frontend
npm install
```

`npm install` creates or updates `frontend/package-lock.json`. Use `npm ci` for
repeatable installs after the lockfile has been committed.

## Development server

Start the backend in one terminal from the repository root:

```bash
uvicorn backend.api.app:app --reload
```

Start Vite in another terminal:

```bash
cd frontend
npm run dev
```

The Vite server proxies requests beginning with `/api` to
`http://127.0.0.1:8000`. The proxy keeps browser requests same-origin from the
frontend's point of view. If the backend runs elsewhere, set the documented Vite
override before starting Vite:

```bash
VITE_API_BASE_URL=http://127.0.0.1:9000 npm run dev
```

Production normally leaves `VITE_API_BASE_URL` unset so the browser uses
same-origin relative `/api` URLs.

## Production build

```bash
cd frontend
npm ci
npm run build
```

The build writes `frontend/dist/index.html` and its hashed assets. The FastAPI
application conditionally mounts that directory at `/` when it exists, while
keeping `/api` routes ahead of the SPA fallback.

To serve the built explorer through FastAPI, build first and then run from the
repository root:

```bash
cd frontend && npm run build
cd ..
uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Run IDs are loaded from `GET /api/runs`; detail,
lineage, and PNG requests remain relative to that same origin. The add-run form
accepts a server filesystem path. A browser folder picker cannot expose a
server filesystem path, so the explorer does not pretend that it can.

## Scope note

The frontend intentionally has no heavy scientific Python or plotting stack.
PNG rendering remains a backend responsibility. The connection endpoint's
labeled unavailable placeholder is rendered like any other valid PNG when the
optional bound-statistic dependencies are not installed.
