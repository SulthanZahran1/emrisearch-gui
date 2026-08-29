"""Option-A run-root resolution and persistent add-run configuration."""

import json

from backend.emri import (
    load_config,
    register_run_path,
    resolve_run_root,
    resolve_run_roots,
    save_config,
)


def test_config_file_is_read_and_environment_root_wins(tmp_path, monkeypatch):
    config_path = tmp_path / "backend" / "config.json"
    configured = tmp_path / "configured"
    extra = tmp_path / "extra"
    environment = tmp_path / "environment"
    save_config({"run_root": str(configured), "extra_runs": [str(extra)]}, config_path)

    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    assert resolve_run_root(config_path) == configured.resolve()
    assert resolve_run_roots(config_path) == (configured.resolve(), extra.resolve())
    assert load_config(config_path) == {
        "run_root": str(configured),
        "extra_runs": [str(extra)],
    }

    monkeypatch.setenv("EMRISEARCH_ROOT", str(environment))
    assert resolve_run_root(config_path) == environment.resolve()
    assert resolve_run_roots(config_path) == (environment.resolve(), extra.resolve())


def test_missing_config_means_no_primary_or_extra_roots(tmp_path, monkeypatch):
    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    config_path = tmp_path / "missing" / "config.json"

    assert load_config(config_path) == {"run_root": None, "extra_runs": []}
    assert resolve_run_root(config_path) is None
    assert resolve_run_roots(config_path) == ()


def test_resolved_roots_are_deduplicated_with_primary_first(tmp_path, monkeypatch):
    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    config_path = tmp_path / "config.json"
    primary = tmp_path / "primary"
    extra = tmp_path / "extra"
    save_config(
        {
            "run_root": str(primary),
            "extra_runs": [str(primary), str(extra), str(extra), str(primary)],
        },
        config_path,
    )

    assert resolve_run_roots(config_path) == (primary.resolve(), extra.resolve())


def test_register_run_path_appends_persistently_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    config_path = tmp_path / "config.json"
    primary = tmp_path / "primary"
    first_extra = tmp_path / "first-extra"
    second_extra = tmp_path / "second-extra"
    save_config({"run_root": str(primary), "extra_runs": []}, config_path)

    first = register_run_path(first_extra, config_path)
    second = register_run_path(first_extra, config_path)
    third = register_run_path(second_extra, config_path)

    assert first["extra_runs"] == [str(first_extra.resolve())]
    assert second["extra_runs"] == [str(first_extra.resolve())]
    assert third["extra_runs"] == [str(first_extra.resolve()), str(second_extra.resolve())]
    assert load_config(config_path) == third
    assert json.loads(config_path.read_text(encoding="utf-8")) == third
    assert resolve_run_roots(config_path) == (
        primary.resolve(),
        first_extra.resolve(),
        second_extra.resolve(),
    )


def test_register_run_path_creates_missing_config_and_keeps_primary_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("EMRISEARCH_ROOT", raising=False)
    config_path = tmp_path / "nested" / "config.json"
    run = tmp_path / "run"

    config = register_run_path(run, config_path)

    assert config["run_root"] is None
    assert config["extra_runs"] == [str(run.resolve())]
    assert resolve_run_root(config_path) is None
    assert resolve_run_roots(config_path) == (run.resolve(),)
