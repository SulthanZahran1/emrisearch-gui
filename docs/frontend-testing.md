# Frontend acceptance verification

Issue #11 is the independent acceptance lane for the React explorer. The suite
uses Vitest with jsdom and Testing Library for deterministic component/API
checks. It does not add fixtures or sample data to the product bundle.

## Install and run the suite

From the repository root:

```bash
cd frontend
npm ci
npm test
```

The tests cover the real API client wire contract, encoded nested run IDs,
loading/empty/error/not-found states, chain grouping, visible `unset` values,
add-run status/error handling, lineage, plot request controls and downloads,
theme persistence, and accessible labels.

## Build gate

```bash
cd frontend
npm run build
```

This must produce `frontend/dist/index.html`. The build output is ignored by
git and is served by FastAPI when the directory exists.

## Real browser smoke

The smoke script creates a temporary deterministic run tree with the shipped
numpy-only fixture builder, starts a local Uvicorn process, and drives the
production build through isolated headless Chromium. It removes the temporary
run tree and stops the server on exit.

```bash
cd frontend
npm run build
# Run this once on machines without a cached Playwright browser.
npx playwright install chromium
npm run browser-smoke
```

The script checks discovery, detail and lineage rendering, both server PNGs,
actual corner/connection query URL changes, PNG download wiring, shell theme
persistence, console/page errors, and 390px horizontal overflow. Set
`EMRI_PYTHON` when the backend virtualenv is not at the default local path:

```bash
EMRI_PYTHON=/path/to/python npm run browser-smoke
```

The backend connection plot may legitimately be a labeled placeholder when the
optional heavy statistic stack is unavailable. The browser treats that PNG as a
valid response, not as a client error.
