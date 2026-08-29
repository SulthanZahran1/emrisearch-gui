"""Shape and display-contract tests for the frozen data-layer views."""

import json
from dataclasses import fields

import pytest

from backend.emri import (
    BestPerProcessTable,
    BestPoint,
    BestPointDimension,
    Diagnostics,
    ManifestDetails,
    NSigmaRow,
    NSigmaTable,
    PlotRequest,
    PlotTheme,
    ProcessBest,
    RunDetail,
    RunSummary,
    SampleCounts,
    SearchDimension,
    SearchSpaceTable,
    UNSET,
    build_detail,
    make_manifest_run,
)


def field_names(cls):
    return tuple(item.name for item in fields(cls))


def test_run_summary_field_shape_and_aliases():
    assert field_names(RunSummary) == (
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
    )

    summary = RunSummary(
        id="nested/run",
        path="/tmp/nested/run",
        kind="from_run",
        statistic="pure",
        ndim=5,
        best_log_density=1.25,
        from_run="../parent",
        out="/tmp/nested/run",
        result_kind="parismc_sampler",
        warnings=("warning",),
    )
    assert summary.name == summary.id
    assert summary.run_id == summary.id
    assert summary.seeding_kind == summary.kind
    assert summary.seeding == summary.kind
    assert summary.dims == summary.ndim
    assert summary.statistic_name == summary.statistic
    assert summary.best_ld == summary.best_log_density
    assert summary.best_logdensity == summary.best_log_density
    assert summary.warnings == ("warning",)

    defaults = RunSummary("run", "/tmp/run")
    assert defaults.kind == UNSET
    assert defaults.statistic == UNSET
    assert defaults.result_kind == UNSET
    assert defaults.ndim is None
    assert defaults.best_log_density is None


def test_search_dimension_shape_defaults_and_aliases():
    assert field_names(SearchDimension) == (
        "name",
        "transform",
        "lo",
        "hi",
        "search_coord",
    )
    dimension = SearchDimension("m1", "log10", 5.2, 6.0, "log10_m1")
    assert dimension.search_name == "log10_m1"
    assert dimension.bounds == (5.2, 6.0)

    unset = SearchDimension("m1")
    assert unset.transform == UNSET
    assert unset.lo == UNSET
    assert unset.hi == UNSET
    assert unset.search_coord == UNSET


def test_search_space_table_aliases():
    row = SearchDimension("m1", "log10", 5.2, 6.0, "log10_m1")
    table = SearchSpaceTable(
        dimensions=(row,), fixed={"xI0": 1.0}, truth={"m1": 300000.0}
    )
    assert table.free == (row,)
    assert table.rows == (row,)
    assert table.ndim == 1
    assert table.fixed_params == table.fixed


def test_n_sigma_row_and_table_shapes_and_aliases():
    assert field_names(NSigmaRow) == ("name", "best", "truth", "sigma", "n_sigma")
    row = NSigmaRow("m1", best=5.4, truth=5.477, sigma=0.1, n_sigma=0.77)
    assert row.best_search == row.best
    assert row.truth_search == row.truth
    assert row.value == row.n_sigma
    assert row.distance == row.n_sigma

    table = NSigmaTable(rows=(row,), available=True)
    assert tuple(table) == (row,)
    assert len(table) == 1
    assert table[0] is row
    assert table.values == (row.n_sigma,)


def test_process_best_and_process_table_shapes_and_unset_status():
    assert field_names(ProcessBest) == (
        "process",
        "log_density",
        "search_coordinates",
        "physical_coordinates",
    )
    process = ProcessBest(2, log_density=0.5, search_coordinates=(1.0,))
    assert process.proc == 2
    assert process.ld == process.log_density
    assert process.best_log_density == process.log_density
    assert process.search == process.search_coordinates
    assert process.physical == process.physical_coordinates

    unavailable = BestPerProcessTable()
    assert unavailable.available is False
    assert unavailable.status == UNSET
    assert unavailable.read == UNSET
    assert unavailable.spread == UNSET
    assert tuple(unavailable) == ()

    merged = BestPerProcessTable(rows=(process,), spread=1.0, merged=True, available=True)
    unmerged = BestPerProcessTable(rows=(process,), spread=5.0, merged=False, available=True)
    assert merged.status == merged.read == "merged"
    assert unmerged.status == unmerged.read == "unmerged"


def test_sample_counts_and_run_detail_property_aliases():
    assert field_names(SampleCounts) == ("n_samples", "n_finite")
    counts = SampleCounts(n_samples=32, n_finite=31)
    assert counts.total == 32
    assert counts.finite == 31

    best_row = BestPointDimension("m1", "log10", search=5.4, physical=250000.0)
    best = BestPoint(
        log_density=0.0,
        dimensions=(best_row,),
        search_coordinates=(5.4,),
        physical_coordinates=(250000.0,),
    )
    assert field_names(BestPoint) == (
        "log_density",
        "dimensions",
        "search_coordinates",
        "physical_coordinates",
    )
    assert best.ld == best.best_log_density == 0.0
    assert best.search == best.search_coords == best.search_coordinates == (5.4,)
    assert best.physical == best.physical_coords == best.physical_coordinates == (250000.0,)
    assert best.coords == best.search_coordinates
    assert best.rows == best.dimensions
    assert best.search_by_name == {"m1": 5.4}
    assert best.physical_by_name == {"m1": 250000.0}
    assert best_row.search_coord == best_row.search
    assert best_row.physical_coord == best_row.physical
    assert best_row.sigma == best_row.n_sigma == UNSET

    detail = RunDetail(
        summary=RunSummary("run", "/tmp/run"),
        path="/tmp/run",
        manifest_groups=ManifestDetails(),
        best=best,
        diagnostics=Diagnostics(),
        samples=counts,
    )
    assert detail.manifest_view is detail.manifest_groups
    assert detail.best_point is best
    assert detail.search_space is detail.manifest_groups.space
    assert detail.samples is counts
    assert detail.n_samples == 32
    assert detail.n_finite == 31
    assert detail.ndim == 1
    assert detail.n_sigma_to_contain is detail.diagnostics.n_sigma_to_contain
    assert detail.best_per_process is detail.diagnostics.best_per_process


def test_plot_request_kwargs_are_separate_from_gui_metadata():
    assert field_names(PlotRequest) == (
        "kind",
        "upstream",
        "kwargs",
        "theme",
        "truth",
        "options",
    )
    request = PlotRequest(
        kind="corner",
        upstream="some.function",
        kwargs={"result": object(), "top_n": 10},
        theme=PlotTheme.DARK,
        truth=True,
        options={"theme": "dark", "truth": True},
    )
    assert set(request.kwargs) == {"result", "top_n"}
    assert request.theme is PlotTheme.DARK
    assert request.truth is True
    assert request.render_options == {"theme": "dark", "truth": True}
    assert request.for_upstream() == request.kwargs
    assert request.for_upstream() is not request.kwargs
    assert request.plot_type == request.type == "corner"
    assert request.target == request.upstream
    assert request.params == request.upstream_kwargs == request.kwargs

    assert {theme.value for theme in PlotTheme} == {"default", "dark", "paper"}
    assert PlotTheme("default") is PlotTheme.DEFAULT


def test_null_and_absent_manifest_values_become_unset_only_in_display_view(tmp_path):
    run = make_manifest_run(tmp_path / "run", kind="lhs_tuple", seed=0)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["emrisearch_version"] = None
    manifest["source"]["m2"] = None
    manifest["modes"]["M_mode"] = None
    manifest["out"] = None
    manifest.pop("noise")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    detail = build_detail(run, root=tmp_path)

    # The raw JSON is the source of truth and remains null/absent.
    assert detail.manifest["emrisearch_version"] is None
    assert detail.manifest["source"]["m2"] is None
    assert detail.manifest["modes"]["M_mode"] is None
    assert detail.manifest["out"] is None
    assert "noise" not in detail.manifest

    groups = detail.manifest_groups
    assert groups.emrisearch_version == UNSET
    assert groups.source["m2"] == UNSET
    assert groups.modes["M_mode"] == UNSET
    assert groups.out == UNSET
    assert groups.noise == {}
    assert groups.search_space is groups.space
    assert groups.version == UNSET
    assert groups.fixed_params == groups.space.fixed
    assert groups.observation_noise_modes == {
        **{f"obs.{key}": value for key, value in groups.obs.items()},
        **{f"modes.{key}": value for key, value in groups.modes.items()},
    }


def test_frozen_dataclass_views_reject_mutation():
    with pytest.raises((AttributeError, TypeError)):
        RunSummary("run", "/tmp/run").id = "changed"
