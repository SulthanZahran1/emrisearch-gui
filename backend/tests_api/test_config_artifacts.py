"""HTTP contract tests for the generate-only config artifact endpoints."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.api import app as app_module
from backend.emri import canonical_config, normalize_config
from backend.emri.config_builder import ArtifactBundle, build_artifacts


def _canonical_payload(out: str = "/scratch/emri/emri_c_stage1_s12") -> dict:
    return canonical_config(out=out)


def test_canonical_preset_returns_upstream_vocabulary(client):
    response = client.get("/api/configs/canonical")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "source", "obs", "noise", "modes", "statistic", "space",
        "sampler", "seeding", "out", "pbs",
    }
    assert payload["source"]["preset"] == "emri_c"
    assert payload["obs"] == {
        "T": 8 / 12, "dt": 5, "tdi_gen": 1, "use_gpu": True, "pad_output": False,
    }
    names = [row["name"] for row in payload["space"]["free"]]
    assert names == ["m1", "m2", "a", "p0", "e0"]
    assert [row["transform"] for row in payload["space"]["free"]] == [
        "log10", "log10", "identity", "identity", "identity",
    ]
    assert payload["statistic"] == {"kind": "semicoherent", "options": {"N_seg": 12}}
    assert payload["seeding"] == {"kind": "internal_lhs", "n": 1000, "batch_size": 10}
    assert payload["sampler"]["n_seed"] == 10
    assert payload["sampler"]["seed"] == 6342


def test_preview_returns_deterministic_artifacts_without_writing(client):
    payload = _canonical_payload()
    first = client.post("/api/configs/preview", json={"config": payload})
    assert first.status_code == 200
    body = first.json()
    assert body["saved"] is False
    assert body["written_paths"] == []
    assert set(body["artifacts"]) == {"python", "pbs"}
    assert body["artifacts"]["python"]["filename"].endswith(".py")
    assert body["artifacts"]["pbs"]["filename"].endswith(".pbs")

    second = client.post("/api/configs/preview", json={"config": payload})
    assert second.json()["artifacts"] == body["artifacts"]


def test_preview_creates_no_files(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = _canonical_payload(out=str(tmp_path / "out"))
    response = client.post("/api/configs/preview", json={"config": payload})
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_minimal_config_merges_preset_defaults(client):
    """A bare config (only out) uses every preset default, including PBS."""
    response = client.post(
        "/api/configs/preview",
        json={"config": {"out": "/scratch/emri/demo"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["saved"] is False
    assert body["artifacts"]["pbs"]["filename"] == "run_emri_c_semicoherent.pbs"
    assert body["config"]["pbs"]["project"] == "CFP03-CF-051"
    # Explicitly-supplied PBS values still win over defaults.
    response = client.post(
        "/api/configs/preview",
        json={
            "config": {
                "out": "/scratch/emri/demo",
                "pbs": {"project": "MY-PROJ"},
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["config"]["pbs"]["project"] == "MY-PROJ"


def test_preset_empty_output_path_follows_out(client):
    """The UI preset carries pbs.output_path=\"\"; it must track a filled out."""
    payload = canonical_config(out="/scratch/emri/ui-filled")
    response = client.post("/api/configs/preview", json={"config": payload})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["config"]["pbs"]["output_path"] == "/scratch/emri/ui-filled"
    assert f"EMRISEARCH_OUT=/scratch/emri/ui-filled" in body["artifacts"]["pbs"]["content"]
    # A non-matching explicit output_path is still rejected.
    payload["pbs"]["output_path"] = "/other"
    response = client.post("/api/configs/preview", json={"config": payload})
    assert response.status_code == 422, response.text
    assert "pbs.output_path" in response.json()["detail"]


def test_invalid_configs_return_field_qualified_422(client):
    cases = {
        "empty out": _canonical_payload(out=""),
        "missing out": {k: v for k, v in _canonical_payload().items() if k != "out"},
        "unknown top-level field": {**_canonical_payload(), "bogus": 1},
        "unknown nested field": {
            **_canonical_payload(),
            "obs": {**_canonical_payload()["obs"], "bogus": True},
        },
        "dt too coarse": {
            **_canonical_payload(),
            "obs": {**_canonical_payload()["obs"], "dt": 100},
        },
        "bad tdi_gen": {
            **_canonical_payload(),
            "obs": {**_canonical_payload()["obs"], "tdi_gen": 3},
        },
        "bad transform": {
            **_canonical_payload(),
            "space": {
                **_canonical_payload()["space"],
                "free": [
                    {**row, "transform": "identity"} if row["name"] == "m1" else row
                    for row in _canonical_payload()["space"]["free"]
                ],
            },
        },
        "lo >= hi": {
            **_canonical_payload(),
            "space": {
                **_canonical_payload()["space"],
                "free": [
                    {**row, "lo": 7.0, "hi": 6.5} if row["name"] == "m1" else row
                    for row in _canonical_payload()["space"]["free"]
                ],
            },
        },
        "wrong free shape": {
            **_canonical_payload(),
            "space": {
                **_canonical_payload()["space"],
                "free": _canonical_payload()["space"]["free"][:-1],
            },
        },
        "wrong statistic kind": {
            **_canonical_payload(),
            "statistic": {"kind": "pure", "options": {}},
        },
        "zero N_seg": {
            **_canonical_payload(),
            "statistic": {"kind": "semicoherent", "options": {"N_seg": 0}},
        },
        "wrong seeding kind": {
            **_canonical_payload(),
            "seeding": {"kind": "from_run", "path": "/x", "n_sigma": 5},
        },
        "merge_confidence too high": {
            **_canonical_payload(),
            "sampler": {**_canonical_payload()["sampler"], "merge_confidence": 1.5},
        },
        "bogus exclude_scale_z": {
            **_canonical_payload(),
            "sampler": {**_canonical_payload()["sampler"], "exclude_scale_z": "bogus"},
        },
        "bad walltime": {
            **_canonical_payload(),
            "pbs": {**_canonical_payload()["pbs"], "walltime": "25:00:99"},
        },
        "shell metacharacters in project": {
            **_canonical_payload(),
            "pbs": {**_canonical_payload()["pbs"], "project": "x; rm -rf /"},
        },
        "python filename with separator": {
            **_canonical_payload(),
            "pbs": {**_canonical_payload()["pbs"], "python_filename": "../evil.py"},
        },
        "traversal in out": _canonical_payload(out="/tmp/../etc/passwd"),
        "traversal in pbs venv": {
            **_canonical_payload(),
            "pbs": {**_canonical_payload()["pbs"], "venv_activate": "/tmp/../../x/activate"},
        },
    }
    for label, payload in cases.items():
        response = client.post("/api/configs/preview", json={"config": payload})
        assert response.status_code == 422, label
        detail = response.json()["detail"]
        assert isinstance(detail, str) and detail.strip(), label


def test_save_writes_exactly_two_files_then_conflicts_then_overwrites(client, tmp_path):
    payload = _canonical_payload()
    first = client.post("/api/configs/save", json={"config": payload, "artifact_dir": str(tmp_path)})
    assert first.status_code == 200
    body = first.json()
    assert body["saved"] is True
    assert len(body["written_paths"]) == 2
    files = sorted(path.name for path in tmp_path.iterdir())
    assert files == ["run_emri_c_semicoherent.pbs", "run_emri_c_semicoherent.py"]

    # Saved bytes match the deterministic preview bytes exactly.
    preview = client.post("/api/configs/preview", json={"config": payload}).json()
    saved_py = (tmp_path / "run_emri_c_semicoherent.py").read_text()
    saved_pbs = (tmp_path / "run_emri_c_semicoherent.pbs").read_text()
    assert saved_py == preview["artifacts"]["python"]["content"]
    assert saved_pbs == preview["artifacts"]["pbs"]["content"]

    # No-overwrite default: conflict.
    conflict = client.post("/api/configs/save", json={"config": payload, "artifact_dir": str(tmp_path)})
    assert conflict.status_code == 409
    assert "overwrite" in conflict.json()["detail"]

    # Explicit opt-in replace.
    replaced = client.post(
        "/api/configs/save",
        json={"config": payload, "artifact_dir": str(tmp_path), "overwrite": True},
    )
    assert replaced.status_code == 200
    assert replaced.json()["written_paths"] == body["written_paths"]


def test_save_rejects_unsafe_or_invalid_targets(client, tmp_path):
    payload = _canonical_payload()

    blocking_file = tmp_path / "not-a-dir"
    blocking_file.write_text("x")
    response = client.post(
        "/api/configs/save",
        json={"config": payload, "artifact_dir": str(blocking_file)},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/configs/save",
        json={"config": payload, "artifact_dir": str(tmp_path / ".." / ".." / "etc")},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/configs/save",
        json={"config": payload, "artifact_dir": ""},
    )
    assert response.status_code == 422


def test_generated_python_is_inert_and_guard_gated(client):
    payload = _canonical_payload()
    content = client.post("/api/configs/preview", json={"config": payload}).json()[
        "artifacts"
    ]["python"]["content"]
    tree = ast.parse(content)

    heavy = {"few", "emrisearch", "parismc", "lisatools", "fastlisaresponse"}
    top_level_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_level_imports.append(node.module or "")
    assert not (heavy & set(top_level_imports))

    in_main = False
    execute_lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
            in_main = True
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "execute":
            execute_lines.append(node.lineno)
    assert execute_lines, "run.execute() must be present inside main()"
    assert in_main

    guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in tree.body
    )
    assert guard


def test_generated_pbs_is_deferred_and_unsubmitting(client):
    payload = _canonical_payload()
    content = client.post("/api/configs/preview", json={"config": payload}).json()[
        "artifacts"
    ]["pbs"]["content"]
    assert "#PBS -P " in content
    assert "#PBS -N " in content
    assert "#PBS -l walltime=" in content
    assert "#PBS -l select=1:ngpus=" in content
    assert "module load " in content
    assert "source " in content
    assert "export EMRISEARCH_OUT=" in content
    assert "qsub" not in content
    assert "sbatch" not in content
    # Generated scripts must never carry credentials.
    assert "token" not in content.lower()
    assert "secret" not in content.lower()
