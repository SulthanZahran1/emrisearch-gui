"""POST /api/runs validation, idempotency, and persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.emri as emri
from backend.api import app as app_module
from backend.emri import make_manifest_run
from backend.emri import root as root_module


@pytest.fixture(autouse=True)
def fake_config_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Replace the data-layer config store so tests never write backend/config.json."""
    store = {"run_root": None, "extra_runs": []}
    writes: list[dict] = []
    scratch_config = tmp_path / "config.json"

    def load_config(_path=None):
        return {
            "run_root": store["run_root"],
            "extra_runs": list(store["extra_runs"]),
        }

    def save_config(config, _path=None):
        store["run_root"] = config.get("run_root")
        store["extra_runs"] = list(config.get("extra_runs", []))
        saved = {
            "run_root": store["run_root"],
            "extra_runs": list(store["extra_runs"]),
        }
        writes.append(saved)
        return saved

    monkeypatch.setattr(root_module, "CONFIG_PATH", scratch_config)
    monkeypatch.setattr(root_module, "load_config", load_config)
    monkeypatch.setattr(root_module, "save_config", save_config)
    # app._is_registered imports this package-level name dynamically.
    monkeypatch.setattr(emri, "load_config", load_config)
    return store, writes, scratch_config


def _assert_error(response, expected_detail: str | None = None):
    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"detail"}
    assert isinstance(payload["detail"], str)
    if expected_detail is not None:
        assert payload["detail"] == expected_detail


def test_post_runs_rejects_empty_path(client, fake_config_store):
    response = client.post("/api/runs", json={"path": "   "})

    _assert_error(response, "path must not be empty")
    assert fake_config_store[0]["extra_runs"] == []


def test_post_runs_rejects_non_directory_path(client, fake_config_store, tmp_path):
    missing = tmp_path / "missing-run"

    response = client.post("/api/runs", json={"path": str(missing)})

    _assert_error(response, f"run path is not a directory: {missing}")
    assert fake_config_store[0]["extra_runs"] == []


def test_post_runs_rejects_directory_without_a_run_marker(
    client, fake_config_store, tmp_path
):
    directory = tmp_path / "not-a-run"
    directory.mkdir()
    (directory / "notes.txt").write_text("not a run", encoding="utf-8")

    response = client.post("/api/runs", json={"path": str(directory)})

    _assert_error(
        response,
        f"run path must contain manifest.json or sampler_state.pkl: {directory}",
    )
    assert fake_config_store[0]["extra_runs"] == []


def test_post_runs_rejects_directory_where_marker_is_not_a_file(
    client, fake_config_store, tmp_path
):
    directory = tmp_path / "invalid-marker"
    directory.mkdir()
    (directory / "manifest.json").mkdir()

    response = client.post("/api/runs", json={"path": str(directory)})

    _assert_error(
        response,
        f"run path must contain manifest.json or sampler_state.pkl: {directory}",
    )
    assert fake_config_store[0]["extra_runs"] == []


def test_post_runs_registers_new_path_and_persists_it_in_config_store(
    client, configure_roots, fake_config_store, tmp_path
):
    run = make_manifest_run(tmp_path / "runs" / "new", kind="lhs_tuple", seed=0)
    configure_roots(run.parent)

    response = client.post("/api/runs", json={"path": str(run)})

    assert response.status_code == 201
    summary = response.json()
    assert summary["id"] == "new"
    assert summary["path"] == str(run.resolve())
    assert summary["kind"] == "internal_lhs"
    assert fake_config_store[0]["extra_runs"] == [str(run.resolve())]
    assert fake_config_store[1] == [
        {
            "run_root": None,
            "extra_runs": [str(run.resolve())],
        }
    ]
    assert not fake_config_store[2].exists()


def test_post_runs_is_idempotent_and_second_registration_returns_200(
    client, configure_roots, fake_config_store, tmp_path
):
    run = make_manifest_run(tmp_path / "runs" / "same", kind="lhs_tuple", seed=1)
    configure_roots(run.parent)

    first = client.post("/api/runs", json={"path": str(run)})
    second = client.post("/api/runs", json={"path": str(run)})

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()
    assert fake_config_store[0]["extra_runs"] == [str(run.resolve())]
    assert len(fake_config_store[1]) == 2
    assert all(
        saved["extra_runs"] == [str(run.resolve())]
        for saved in fake_config_store[1]
    )


def test_post_runs_accepts_a_run_already_scanned_from_emrisearch_root(
    client, fake_config_store, monkeypatch, tmp_path
):
    root = tmp_path / "environment-root"
    run = make_manifest_run(root / "from-env", kind="lhs_tuple", seed=2)
    monkeypatch.setenv("EMRISEARCH_ROOT", str(root))
    # Restore the real resolver for this test so the environment-root branch is
    # exercised rather than the default empty-root fixture isolation.
    monkeypatch.setattr(app_module, "resolve_run_roots", root_module.resolve_run_roots)

    first = client.post("/api/runs", json={"path": str(run)})
    second = client.post("/api/runs", json={"path": str(run)})

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"] == "from-env"
    assert fake_config_store[0]["extra_runs"] == [str(run.resolve())]
