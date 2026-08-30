"""HTTP contract tests for the server-side corner PNG endpoint."""

from __future__ import annotations

import pytest

from backend.emri import make_manifest_run


@pytest.fixture
def plot_run(configure_roots, tmp_path):
    root = tmp_path / "runs"
    run = make_manifest_run(root / "corner-run", kind="parismc_sampler", seed=0)
    configure_roots(root)
    return run


def _corner_url(run_id: str = "corner-run") -> str:
    return f"/api/runs/{run_id}/plots/corner"


def _assert_png(response):
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) > 1_000
    assert "cache-control" not in response.headers
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"theme": "default"},
        {"theme": "dark"},
        {"theme": "paper"},
        {"truth": "true"},
        {"truth": "false"},
        {"annotate": "false"},
        {
            "theme": "paper",
            "truth": "false",
            "annotate": "false",
            "top_n": 100,
            "title": "Custom corner title",
        },
        {"top_n": 100},
        {"title": "Custom corner title"},
    ],
)
def test_corner_endpoint_renders_png_for_supported_controls(client, plot_run, params):
    response = client.get(_corner_url(), params=params)

    _assert_png(response)


def test_corner_endpoint_themes_produce_distinct_png_bytes(client, plot_run):
    images = {
        theme: client.get(_corner_url(), params={"theme": theme}).content
        for theme in ("default", "dark", "paper")
    }

    assert all(image.startswith(b"\x89PNG\r\n\x1a\n") for image in images.values())
    # Corner figures never draw grids: the accepted prototype's corner_plot
    # has no grid call (prototype/make_figs.py:129-161), so default and paper
    # share the same light recipe and serialize identically by design. The
    # theme distinction that matters is dark vs light.
    assert len(set(images.values())) == 2
    assert images["default"] == images["paper"]
    assert images["dark"] != images["default"]


@pytest.mark.parametrize("theme", ["neon", "", "DEFAULT"])
def test_corner_endpoint_rejects_unknown_theme(client, plot_run, theme):
    response = client.get(_corner_url(), params={"theme": theme})

    assert response.status_code == 422
    assert response.json() == {
        "detail": "theme must be one of: default, dark, paper"
    }


@pytest.mark.parametrize("top_n", [0, -1])
def test_corner_endpoint_rejects_non_positive_top_n(client, plot_run, top_n):
    response = client.get(_corner_url(), params={"top_n": top_n})

    assert response.status_code == 422
    assert set(response.json()) == {"detail"}
    assert isinstance(response.json()["detail"], str)


def test_corner_endpoint_returns_exact_not_found_error(client, configure_roots, tmp_path):
    configure_roots(tmp_path / "runs")

    response = client.get(_corner_url("unknown"))

    assert response.status_code == 404
    assert response.json() == {"detail": "run not found: unknown"}
