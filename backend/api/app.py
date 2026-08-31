"""FastAPI application for the emrisearch results explorer.

The application is deliberately a thin HTTP adapter over ``backend.emri``.
The data layer owns run discovery, loading, lineage, and request construction;
this module owns validation, response status codes, and optional SPA serving.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
from pathlib import Path
from typing import Any, NoReturn, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import Scope

from backend.emri import (
    ArtifactConflictError,
    ArtifactPathError,
    ConfigValidationError,
    PlotTheme,
    RunSummary,
    build_detail,
    build_artifacts,
    canonical_config,
    chain_of,
    connection_request,
    corner_request,
    generate_config_artifacts,
    get_scan_warnings,
    normalize_config,
    register_run_path,
    resolve_run_roots,
    scan_run_root,
    summarize_run,
    write_artifacts,
)

from .plots import connection_png, corner_png
from .serialization import serialize_run_detail, serialize_run_summary, to_jsonable


app = FastAPI(title="emrisearch explorer API")


class AddRunRequest(BaseModel):
    """Request body for registering an additional run directory."""

    path: str


class ArtifactPreviewRequest(BaseModel):
    """Request body for generating config/artifact previews without writes."""

    config: dict[str, Any]


class ArtifactSaveRequest(BaseModel):
    """Request body for generating and writing artifacts to an explicit path."""

    config: dict[str, Any]
    artifact_dir: str
    overwrite: bool = False


@dataclass(frozen=True)
class _LocatedRun:
    path: Path
    root: Path
    summary: Any


class _SPAStaticFiles(StaticFiles):
    """StaticFiles with a Vite-style index fallback for client-side routes."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code != 404 or scope.get("method") not in {"GET", "HEAD"}:
            return response
        request_path = str(scope.get("path", ""))
        # Keep unknown API paths as JSON 404s rather than returning the SPA shell.
        if request_path == "/api" or request_path.startswith("/api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await super().get_response("index.html", scope)


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid request"
    error = errors[0]
    message = str(error.get("msg", "invalid request"))
    location = error.get("loc", ())
    if location:
        rendered = ".".join(str(part) for part in location if part != "body")
        if rendered:
            return f"{rendered}: {message}"
    return message


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Use the API's documented ``{"detail": string}`` error shape."""
    return JSONResponse(
        status_code=422,
        content={"detail": _validation_message(exc)},
    )


def _unprocessable(message: str) -> NoReturn:
    raise HTTPException(status_code=422, detail=message)


def _selected_theme(value: str) -> PlotTheme:
    try:
        return PlotTheme(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="theme must be one of: default, dark, paper",
        ) from exc


def _scan_all() -> tuple[tuple[Path, ...], list[Any], list[str]]:
    """Scan every configured root, retaining warnings from each scan."""
    warnings: list[str] = []
    try:
        roots = tuple(resolve_run_roots())
    except Exception as exc:
        return (), [], [f"could not resolve run roots: {exc}"]

    summaries: list[Any] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for root in roots:
        try:
            found = scan_run_root(root)
            warnings.extend(str(item) for item in get_scan_warnings())
        except Exception as exc:
            warnings.append(f"could not scan run root {root}: {exc}")
            continue
        for summary in found:
            summary_id = str(getattr(summary, "id", ""))
            summary_path = str(getattr(summary, "path", ""))
            if summary_id in seen_ids or summary_path in seen_paths:
                continue
            seen_ids.add(summary_id)
            seen_paths.add(summary_path)
            summaries.append(summary)
    return roots, summaries, list(dict.fromkeys(warnings))


def _safe_candidate(root: Path, run_id: str) -> Optional[Path]:
    """Resolve a relative run id below one configured root, if it is safe."""
    if not run_id or Path(run_id).is_absolute():
        return None
    root_path = root.expanduser().resolve(strict=False)
    candidate = (root_path / Path(run_id)).resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    if not any((candidate / marker).is_file() for marker in ("manifest.json", "sampler_state.pkl")):
        return None
    return candidate


def _root_containing(path: Path, roots: tuple[Path, ...]) -> Optional[Path]:
    resolved = path.expanduser().resolve(strict=False)
    for root in roots:
        root_path = root.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(root_path)
        except ValueError:
            continue
        return root_path
    return None


def _locate_run(run_id: str) -> Optional[_LocatedRun]:
    roots, summaries, _warnings = _scan_all()
    normalized_id = run_id.rstrip("/")

    for summary in summaries:
        summary_id = str(getattr(summary, "id", ""))
        if summary_id.rstrip("/") != normalized_id:
            continue
        path = Path(str(summary.path)).expanduser().resolve(strict=False)
        root = _root_containing(path, roots)
        if root is None:
            root = path.parent
        return _LocatedRun(path=path, root=root, summary=summary)

    # A direct resolution keeps detail/plot routes useful even if a run was
    # added between a scan and this request, while still preventing traversal.
    for root in roots:
        candidate = _safe_candidate(root, run_id)
        if candidate is None:
            continue
        try:
            summary = summarize_run(candidate, root=root)
        except Exception:
            relative_id = candidate.relative_to(root.expanduser().resolve(strict=False)).as_posix()
            summary = RunSummary(
                id=relative_id or candidate.name,
                path=str(candidate),
            )
        return _LocatedRun(path=candidate, root=root, summary=summary)
    return None


def _not_found(run_id: str) -> NoReturn:
    raise HTTPException(status_code=404, detail=f"run not found: {run_id}")


def _load_detail(run_id: str) -> tuple[_LocatedRun, Any]:
    located = _locate_run(run_id)
    if located is None:
        _not_found(run_id)
    try:
        detail = build_detail(located.path, root=located.root)
    except FileNotFoundError:
        _not_found(run_id)
    except Exception as exc:
        _unprocessable(f"could not load run {run_id}: {exc}")
    return located, detail


def _parse_t_range(raw: str) -> tuple[float, float]:
    cleaned = raw.strip()
    if len(cleaned) >= 2 and cleaned[0] in "([" and cleaned[-1] in ")]":
        cleaned = cleaned[1:-1].strip()
    parts = [part for part in re.split(r"[,\s]+", cleaned) if part]
    if len(parts) != 2:
        _unprocessable("t_range must contain exactly two numbers")
    try:
        bounds = (float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="t_range must contain two numbers") from exc
    if not all(math.isfinite(value) for value in bounds):
        _unprocessable("t_range must contain two finite numbers")
    if bounds[1] <= bounds[0]:
        _unprocessable("t_range must have hi > lo")
    return bounds


def _is_registered(path: Path) -> bool:
    """Check the persistent add-run list before calling its idempotent writer."""
    try:
        from backend.emri import load_config

        config = load_config()
        candidate = path.expanduser().resolve(strict=False)
        for value in config.get("extra_runs", []):
            if Path(value).expanduser().resolve(strict=False) == candidate:
                return True
    except Exception:
        # The registration helper remains the source of truth; a config read
        # failure should not prevent the requested idempotent write attempt.
        return False
    return False


def _summary_for_registered_path(path: Path) -> Any:
    roots, summaries, _warnings = _scan_all()
    resolved = path.expanduser().resolve(strict=False)
    for summary in summaries:
        if Path(str(summary.path)).expanduser().resolve(strict=False) == resolved:
            return summary
    root = _root_containing(resolved, roots) or resolved.parent
    return summarize_run(resolved, root=root)


@app.get("/api/runs")
async def list_runs() -> JSONResponse:
    """Return a merged, de-duplicated scan of all configured roots."""
    _roots, summaries, warnings = _scan_all()
    return JSONResponse(
        content={
            "runs": to_jsonable(summaries),
            "warnings": to_jsonable(warnings),
        }
    )


@app.post("/api/runs")
async def add_run(payload: AddRunRequest) -> JSONResponse:
    """Register an additional run directory in the data-layer config."""
    raw_path = payload.path
    if not raw_path.strip():
        _unprocessable("path must not be empty")
    path = Path(raw_path).expanduser().resolve(strict=False)
    if not path.exists() or not path.is_dir():
        _unprocessable(f"run path is not a directory: {raw_path}")
    if not any((path / marker).is_file() for marker in ("manifest.json", "sampler_state.pkl")):
        _unprocessable(
            f"run path must contain manifest.json or sampler_state.pkl: {raw_path}"
        )

    already_registered = _is_registered(path)
    try:
        register_run_path(path)
        summary = _summary_for_registered_path(path)
    except Exception as exc:
        _unprocessable(f"could not register run {raw_path}: {exc}")
    return JSONResponse(
        status_code=200 if already_registered else 201,
        content=serialize_run_summary(summary),
    )


def _artifact_config_errors(exc: ConfigValidationError) -> NoReturn:
    """Map config-builder validation errors to the API's 422 detail shape."""
    detail = exc.detail or "invalid configuration"
    raise HTTPException(status_code=422, detail=detail)


def _artifact_payload(payload: ArtifactPreviewRequest | ArtifactSaveRequest) -> dict[str, Any]:
    """Normalize once so validation errors use field-level messages."""
    try:
        return normalize_config(payload.config)
    except ConfigValidationError as exc:
        _artifact_config_errors(exc)


@app.get("/api/configs/canonical")
async def canonical_config_endpoint() -> JSONResponse:
    """Return the canonical EMRI-C preset with explicit defaults."""
    return JSONResponse(content=canonical_config())


@app.post("/api/configs/preview")
async def config_preview_endpoint(payload: ArtifactPreviewRequest) -> JSONResponse:
    """Validate and render deterministic Python/PBS artifacts without writing."""
    normalized = _artifact_payload(payload)
    bundle = build_artifacts(normalized)
    return JSONResponse(
        content={
            "config": normalized,
            "artifacts": bundle.to_dict(),
            "written_paths": [],
            "saved": False,
        }
    )


@app.post("/api/configs/save")
async def config_save_endpoint(payload: ArtifactSaveRequest) -> JSONResponse:
    """Validate, render, and write artifacts only to an explicit directory."""
    normalized = _artifact_payload(payload)
    bundle = build_artifacts(normalized)
    try:
        written_paths = write_artifacts(
            bundle,
            payload.artifact_dir,
            overwrite=payload.overwrite,
        )
    except ArtifactConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ArtifactPathError, ConfigValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(
        content={
            "config": normalized,
            "artifacts": bundle.to_dict(),
            "written_paths": written_paths,
            "saved": True,
        }
    )


@app.get("/api/runs/{run_id:path}/plots/corner")
async def corner_plot_endpoint(
    run_id: str,
    top_n: int = Query(default=10, ge=1),
    title: Optional[str] = Query(default=None),
    annotate: bool = Query(default=True),
    truth: bool = Query(default=True),
    theme: str = Query(default="default"),
) -> Response:
    """Render the upstream corner recipe as a PNG."""
    selected_theme = _selected_theme(theme)
    _located, detail = _load_detail(run_id)
    try:
        request = corner_request(
            detail,
            top_n=top_n,
            title=title,
            truth=truth,
            theme=selected_theme,
        )
    except (TypeError, ValueError) as exc:
        _unprocessable(str(exc))
    request = replace(
        request,
        kwargs={**dict(request.kwargs), "annotate": bool(annotate)},
    )
    return Response(content=corner_png(detail, request), media_type="image/png")


@app.get("/api/runs/{run_id:path}/plots/connection")
async def connection_plot_endpoint(
    run_id: str,
    n: int = Query(default=81, ge=2),
    t_range: str = Query(default="-0.3,1.3"),
    ylabel: Optional[str] = Query(default=None),
    progress: bool = Query(default=False),
    theme: str = Query(default="default"),
) -> Response:
    """Render a real bound-statistic connection or its explicit placeholder."""
    selected_theme = _selected_theme(theme)
    _located, detail = _load_detail(run_id)
    try:
        request = connection_request(
            detail,
            n=n,
            t_range=_parse_t_range(t_range),
            ylabel=ylabel,
            progress=progress,
        )
    except (TypeError, ValueError) as exc:
        _unprocessable(str(exc))
    request = replace(
        request,
        theme=selected_theme,
        options={**dict(request.options), "theme": selected_theme.value},
    )
    return Response(content=connection_png(detail, request), media_type="image/png")


@app.get("/api/runs/{run_id:path}/lineage")
async def lineage_endpoint(run_id: str) -> JSONResponse:
    """Return the oldest known ancestor followed by forward descendants."""
    located = _locate_run(run_id)
    if located is None:
        _not_found(run_id)
    _roots, summaries, _warnings = _scan_all()
    chain = chain_of(summaries, str(located.summary.id))
    return JSONResponse(content={"chain": to_jsonable(chain)})


@app.get("/api/runs/{run_id:path}")
async def run_detail_endpoint(run_id: str) -> JSONResponse:
    """Return a serializable detail view for one run."""
    _located, detail = _load_detail(run_id)
    return JSONResponse(content=serialize_run_detail(detail))


_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    # Mounted last so all explicit API routes win.  The subclass supplies the
    # SPA fallback for Vite client-side routes while keeping unknown API paths
    # as JSON 404 responses.
    app.mount(
        "/",
        _SPAStaticFiles(directory=str(_FRONTEND_DIST), html=True),
        name="frontend",
    )


__all__ = ["app"]
