"""HTTP contract tests for the unavailable bound-statistic connection plot."""

from __future__ import annotations

import pytest

from backend.api.plots import CONNECTION_UNAVAILABLE_MESSAGE
from backend.emri import make_manifest_run


@pytest.fixture
def plot_run(configure_roots, tmp_path):
    root = tmp_path / "runs"
    run = make_manifest_run(root / "connection-run", kind="parismc_sampler", seed=0)
    configure_roots(root)
    return run


def _connection_url(run_id: str = "connection-run") -> str:
    return f"/api/runs/{run_id}/plots/connection"


def _assert_png(response):
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) > 1_000


def test_connection_placeholder_message_is_the_documented_one():
    assert (
        "connection plot unavailable — bound statistic stack not installed"
        in CONNECTION_UNAVAILABLE_MESSAGE
    )


@pytest.mark.parametrize("theme", ["default", "dark", "paper"])
def test_connection_endpoint_renders_themed_placeholder_png(
    client, plot_run, theme
):
    response = client.get(_connection_url(), params={"theme": theme})

    _assert_png(response)


@pytest.mark.parametrize(
    "t_range",
    ["0.0,1.0", "(0.0, 1.0)", "[0.0 1.0]", "-0.5,1.5"],
)
def test_connection_endpoint_accepts_supported_t_range_formats(
    client, plot_run, t_range
):
    response = client.get(
        _connection_url(), params={"n": 161, "t_range": t_range}
    )

    _assert_png(response)


def test_connection_endpoint_themes_produce_distinct_placeholder_png_bytes(
    client, plot_run
):
    images = {
        theme: client.get(_connection_url(), params={"theme": theme}).content
        for theme in ("default", "dark", "paper")
    }

    assert all(image.startswith(b"\x89PNG\r\n\x1a\n") for image in images.values())
    # FINDING (implementation): default and paper currently serialize identically
    # on the unavailable placeholder path because their differing grid recipe is
    # not visible while the placeholder axes are disabled. Keep this hard
    # assertion to pin the documented theme distinction.
    assert len(set(images.values())) == 3


@pytest.mark.parametrize(
    "params",
    [
        {"n": 1},
        {"t_range": "5,2"},
        {"t_range": "abc"},
        {"t_range": "1"},
        {"t_range": "1,2,3"},
        {"theme": "neon"},
    ],
)
def test_connection_endpoint_rejects_invalid_query_values(client, plot_run, params):
    response = client.get(_connection_url(), params=params)

    assert response.status_code == 422
    assert set(response.json()) == {"detail"}
    assert isinstance(response.json()["detail"], str)


def test_connection_endpoint_returns_exact_not_found_error(
    client, configure_roots, tmp_path
):
    configure_roots(tmp_path / "runs")

    response = client.get(_connection_url("unknown"))

    assert response.status_code == 404
    assert response.json() == {"detail": "run not found: unknown"}
