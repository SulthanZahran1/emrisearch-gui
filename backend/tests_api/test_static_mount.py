"""The API remains usable when the optional frontend build is absent."""

from __future__ import annotations

from pathlib import Path

from backend.api import app as app_module


def test_standalone_app_has_no_frontend_dist_and_unknown_api_is_json(client):
    assert not Path(app_module._FRONTEND_DIST).is_dir()
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "if _FRONTEND_DIST.is_dir():" in source

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_standalone_app_still_serves_the_api(client):
    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"runs": [], "warnings": []}
