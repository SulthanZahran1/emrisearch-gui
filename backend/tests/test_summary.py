"""Manifest-only and cheap legacy summary behavior."""

import json
from pathlib import Path

import pytest

from backend.emri import (
    UNSET,
    make_legacy_run,
    make_manifest_run,
    summarize_run,
)
from backend.emri import summary as summary_module


def test_manifest_summary_is_fast_and_does_not_touch_state_file(tmp_path, monkeypatch):
    run = make_manifest_run(tmp_path / "manifest-only", kind="parismc_sampler", seed=3)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    (run / "sampler_state.pkl").unlink()

    original_open = Path.open

    def forbid_state_open(self, *args, **kwargs):
        if self.name == "sampler_state.pkl":
            raise AssertionError("manifest summary must not open sampler_state.pkl")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_state_open)
    monkeypatch.setattr(
        summary_module.pickle,
        "loads",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("manifest summary must not deserialize state")
        ),
    )

    summary = summarize_run(run, root=tmp_path)

    assert summary.id == "manifest-only"
    assert summary.path == str(run.resolve())
    assert summary.kind == manifest["seeding"]["kind"] == "internal_lhs"
    assert summary.statistic == manifest["statistic"]["kind"] == "pure"
    assert summary.ndim == len(manifest["space"]["free"]) == 5
    assert summary.best_log_density is None
    assert summary.from_run is None
    assert summary.out == manifest["out"]
    assert summary.result_kind == UNSET


@pytest.mark.parametrize(
    ("kind", "result_kind"),
    (
        ("lhs_tuple", "lhs_tuple"),
        ("lhs_dict", "lhs_dict"),
        ("npz", "npz"),
    ),
)
def test_legacy_summary_uses_only_cheap_self_describing_shapes(tmp_path, kind, result_kind):
    run = make_legacy_run(tmp_path / kind, kind=kind, seed=0)

    summary = summarize_run(run, root=tmp_path)

    assert summary.id == kind
    assert summary.kind == "legacy"
    assert summary.statistic == UNSET
    assert summary.ndim == 5
    assert summary.best_log_density == pytest.approx(0.0)
    assert summary.from_run is None
    assert summary.out == str(run.resolve())
    assert summary.result_kind == result_kind


def test_legacy_parismc_summary_never_deserializes_the_sampler(tmp_path, monkeypatch):
    run = make_legacy_run(tmp_path / "legacy-paris", kind="parismc_sampler", seed=0)

    def fail(*_args, **_kwargs):
        raise AssertionError("legacy parismc summary must not deserialize state")

    monkeypatch.setattr(summary_module.pickle, "load", fail)
    monkeypatch.setattr(summary_module.pickle, "loads", fail)

    summary = summarize_run(run, root=tmp_path)

    assert summary.kind == "legacy"
    assert summary.result_kind == UNSET
    assert summary.ndim is None
    assert summary.best_log_density is None


def test_manifest_from_run_pointer_is_exposed_for_lineage_wiring(tmp_path):
    parent = make_manifest_run(tmp_path / "stage_00", kind="parismc_sampler", seed=0)
    child = make_manifest_run(tmp_path / "stage_01", kind="parismc_sampler", seed=1)
    manifest_path = child / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["seeding"] = {"kind": "from_run", "path": "../stage_00", "n_sigma": 3.0}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = summarize_run(child, root=tmp_path)

    assert summary.id == "stage_01"
    assert summary.from_run == "../stage_00"
    assert summary.kind == "from_run"
    # out is the manifest field verbatim (".", the fixture's relative value),
    # exactly as a real run's absolute out is surfaced without rewriting.
    assert summary.out == "."
    assert parent.name in summary.from_run
