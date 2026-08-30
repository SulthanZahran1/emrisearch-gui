"""HTTP tests for run discovery, detail views, and lineage."""

from __future__ import annotations

from urllib.parse import quote

from backend.api import app as app_module
from backend.emri import make_legacy_run, make_manifest_run, make_run_chain
from backend.emri import root as root_module


def test_get_runs_returns_empty_envelope_without_configured_roots(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(root_module, "CONFIG_PATH", tmp_path / "missing" / "config.json")
    monkeypatch.setattr(app_module, "resolve_run_roots", root_module.resolve_run_roots)

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.json() == {"runs": [], "warnings": []}


def test_get_runs_merges_a_fixture_chain_in_sorted_order(client, configure_roots, tmp_path):
    root = tmp_path / "runs"
    paths = make_run_chain(root, n_stages=3)
    configure_roots(root)

    response = client.get("/api/runs")

    assert response.status_code == 200
    payload = response.json()
    assert [run["id"] for run in payload["runs"]] == [
        "stage_00",
        "stage_01",
        "stage_02",
    ]
    assert [run["path"] for run in payload["runs"]] == [
        str(path.resolve()) for path in paths
    ]
    assert [run["kind"] for run in payload["runs"]] == [
        "internal_lhs",
        "from_run",
        "from_run",
    ]
    assert payload["warnings"] == []


def test_get_runs_discovers_legacy_lhs_tuple_state(client, configure_roots, tmp_path):
    root = tmp_path / "runs"
    legacy = make_legacy_run(root / "legacy", kind="lhs_tuple", seed=4)
    configure_roots(root)

    payload = client.get("/api/runs").json()

    assert payload["runs"] == [
        {
            "id": "legacy",
            "path": str(legacy.resolve()),
            "kind": "legacy",
            "statistic": "unset",
            "ndim": 5,
            "best_log_density": 0.0,
            "from_run": None,
            "out": str(legacy.resolve()),
            "result_kind": "lhs_tuple",
            "warnings": [],
        }
    ]
    assert payload["warnings"] == []


def test_get_runs_deduplicates_a_path_seen_through_two_roots(
    client, configure_roots, tmp_path
):
    root = tmp_path / "runs"
    run = make_manifest_run(root / "shared", kind="lhs_tuple", seed=0)
    alias = tmp_path / "runs-alias"
    alias.symlink_to(root, target_is_directory=True)
    configure_roots(root, alias)

    payload = client.get("/api/runs").json()

    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["id"] == "shared"
    assert payload["runs"][0]["path"] == str(run.resolve())
    assert payload["warnings"] == []


def test_get_runs_surfaces_broken_candidate_without_aborting_other_runs(
    client, configure_roots, tmp_path
):
    root = tmp_path / "runs"
    good = make_manifest_run(root / "good", kind="lhs_tuple", seed=0)
    broken = root / "broken"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{not valid json", encoding="utf-8")
    configure_roots(root, root)

    payload = client.get("/api/runs").json()

    assert [run["id"] for run in payload["runs"]] == ["good"]
    assert len(payload["warnings"]) == 1
    assert str(broken.resolve()) in payload["warnings"][0]
    assert "skipping broken run" in payload["warnings"][0]
    assert str(good.resolve()) == payload["runs"][0]["path"]


def test_get_detail_returns_full_documented_shape_and_excludes_live_objects(
    client, configure_roots, tmp_path
):
    root = tmp_path / "runs"
    run = make_manifest_run(root / "stage_00", kind="parismc_sampler", seed=0)
    configure_roots(root)

    response = client.get("/api/runs/stage_00")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "summary",
        "path",
        "manifest",
        "manifest_groups",
        "best",
        "diagnostics",
        "samples",
        "warnings",
    }
    assert payload["path"] == str(run.resolve())
    assert set(payload["summary"]) == {
        "id",
        "path",
        "kind",
        "statistic",
        "ndim",
        "best_log_density",
        "from_run",
        "out",
        "result_kind",
        "warnings",
    }
    assert payload["summary"]["id"] == "stage_00"
    assert payload["summary"]["ndim"] == 5
    assert payload["samples"] == {"n_samples": 32, "n_finite": 32}
    assert payload["best"]["log_density"] == 0.0
    assert len(payload["best"]["search_coordinates"]) == 5
    assert len(payload["best"]["physical_coordinates"]) == 5
    assert len(payload["best"]["dimensions"]) == 5
    assert set(payload["best"]["dimensions"][0]) == {
        "name",
        "transform",
        "search",
        "physical",
        "n_sigma",
    }
    assert set(payload["diagnostics"]) == {"n_sigma_to_contain", "best_per_process"}
    assert len(payload["diagnostics"]["n_sigma_to_contain"]["rows"]) == 5
    assert len(payload["diagnostics"]["best_per_process"]["rows"]) == 4
    assert set(payload["diagnostics"]["best_per_process"]) == {
        "rows",
        "spread",
        "merged",
        "available",
    }
    assert {
        "source",
        "obs",
        "noise",
        "modes",
        "statistic",
        "space",
        "sampler",
        "seeding",
        "out",
        "emrisearch_version",
        "raw",
    } <= set(payload["manifest_groups"])
    assert "result" not in payload
    assert "param_space" not in payload
    assert payload["warnings"] == []


def test_get_detail_unknown_id_has_exact_error_shape(client, configure_roots, tmp_path):
    configure_roots(tmp_path / "runs")

    response = client.get("/api/runs/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "run not found: does-not-exist"}


def test_get_detail_resolves_nested_id_and_percent_encoded_slash(
    client, configure_roots, tmp_path
):
    root = tmp_path / "runs"
    run = make_manifest_run(
        root / "stage_01" / "replica_a", kind="lhs_tuple", seed=1
    )
    configure_roots(root)
    run_id = "stage_01/replica_a"

    listed = client.get("/api/runs")
    encoded = client.get(f"/api/runs/{quote(run_id, safe='')}")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["runs"]] == [run_id]
    assert encoded.status_code == 200
    assert encoded.json()["summary"]["id"] == run_id
    assert encoded.json()["path"] == str(run.resolve())


def test_get_lineage_returns_oldest_ancestor_through_selected_run_and_descendants(
    client, configure_roots, tmp_path
):
    root = tmp_path / "runs"
    make_run_chain(root, n_stages=3)
    configure_roots(root)

    last = client.get("/api/runs/stage_02/lineage")
    middle = client.get("/api/runs/stage_01/lineage")

    assert last.status_code == middle.status_code == 200
    assert [item["id"] for item in last.json()["chain"]] == [
        "stage_00",
        "stage_01",
        "stage_02",
    ]
    assert [item["id"] for item in middle.json()["chain"]] == [
        "stage_00",
        "stage_01",
        "stage_02",
    ]
    assert all("path" in item and "kind" in item for item in last.json()["chain"])


def test_get_lineage_unknown_id_has_exact_error_shape(client, configure_roots, tmp_path):
    configure_roots(tmp_path / "runs")

    response = client.get("/api/runs/missing/lineage")

    assert response.status_code == 404
    assert response.json() == {"detail": "run not found: missing"}
