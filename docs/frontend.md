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

The frontend always requests relative `/api` paths. During development, Vite
proxies those requests to `http://127.0.0.1:8000` by default, keeping the browser
request same-origin. `VITE_API_BASE_URL` configures this Vite proxy target only;
it is not used as a browser-side API base URL. If the backend runs on another
port, set the variable before starting Vite. For example, with a backend on
port `8766` and Vite on `5176`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8766 npm run dev -- --host 127.0.0.1 --port 5176
```

The production build also uses same-origin relative `/api` URLs; the Vite dev
proxy does not apply to production. Serve the built frontend and backend from
the same origin (as described below), and do not use `VITE_API_BASE_URL` to point
browser requests at a separate origin.

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
