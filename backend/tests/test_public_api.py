"""The documented backend.emri API is importable from the package root."""

import importlib

import pytest


DOCUMENTED_FUNCTIONS = (
    "load_config",
    "save_config",
    "resolve_run_root",
    "resolve_run_roots",
    "register_run_path",
    "scan_run_root",
    "summarize_run",
    "build_detail",
    "chain_of",
    "corner_request",
    "connection_request",
    "n_sigma_to_contain",
    "best_per_process",
)


@pytest.mark.parametrize("name", DOCUMENTED_FUNCTIONS)
def test_documented_function_is_importable_from_package(name):
    module = importlib.import_module("backend.emri")

    assert name in module.__all__
    public = getattr(module, name)
    assert callable(public), name


@pytest.mark.parametrize(
    "name",
    (
        "UNSET",
        "PlotTheme",
        "RunSummary",
        "SearchDimension",
        "NSigmaRow",
        "ProcessBest",
        "SampleCounts",
        "PlotRequest",
        "RunDetail",
    ),
)
def test_public_view_types_are_importable_from_package(name):
    module = importlib.import_module("backend.emri")

    assert name in module.__all__
    assert hasattr(module, name)
