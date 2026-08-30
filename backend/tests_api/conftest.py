"""Shared fixtures for the standalone FastAPI backend API tests."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


app_module = importlib.import_module("backend.api.app")


@pytest.fixture(autouse=True)
def isolate_run_roots(monkeypatch: pytest.MonkeyPatch):
    """Keep every API test independent of the checkout's config file."""
    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    monkeypatch.setattr(app_module, "resolve_run_roots", lambda: ())


@pytest.fixture
def client():
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture
def configure_roots(monkeypatch: pytest.MonkeyPatch):
    """Return a helper that points the imported app at temporary roots."""

    def configure(*roots: Path | str) -> tuple[Path, ...]:
        resolved = tuple(Path(root).resolve() for root in roots)
        monkeypatch.setattr(app_module, "resolve_run_roots", lambda: resolved)
        return resolved

    return configure
