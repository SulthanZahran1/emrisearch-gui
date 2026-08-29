"""Plot request argument and metadata contracts."""

import pytest

from backend.emri import PlotTheme, build_detail, connection_request, corner_request, make_manifest_run


def _detail(tmp_path):
    return build_detail(
        make_manifest_run(tmp_path / "run", kind="parismc_sampler", seed=0),
        root=tmp_path,
    )


def test_corner_request_forwards_only_upstream_kwargs(tmp_path):
    detail = _detail(tmp_path)

    request = corner_request(detail)

    assert request.kind == request.plot_type == request.type == "corner"
    assert request.upstream == request.target == "emrisearch.plotting.corner_plot.plot_result"
    assert set(request.kwargs) == {"result", "space", "top_n", "title", "annotate"}
    assert request.kwargs["result"] is detail.result
    assert request.kwargs["space"] is detail.param_space
    assert request.kwargs["top_n"] == 10
    assert request.kwargs["title"] is None
    assert request.kwargs["annotate"] is True
    assert "truth" not in request.kwargs
    assert "theme" not in request.kwargs
    assert request.truth is True
    assert request.theme is PlotTheme.DEFAULT
    assert request.render_options == {"truth": True, "theme": "default"}
    assert request.for_upstream() == request.kwargs


def test_corner_request_custom_gui_controls_stay_in_metadata(tmp_path):
    detail = _detail(tmp_path)

    request = corner_request(detail, top_n=3, title="run title", truth=False, theme="dark")

    assert request.kwargs == {
        "result": detail.result,
        "space": detail.param_space,
        "top_n": 3,
        "title": "run title",
        "annotate": True,
    }
    assert request.truth is False
    assert request.theme is PlotTheme.DARK
    assert request.options == {"truth": False, "theme": "dark"}
    assert request.render_options == {"truth": False, "theme": "dark"}

    with pytest.raises(ValueError):
        corner_request(detail, theme="neon")
    with pytest.raises(ValueError):
        corner_request(detail, top_n=0)


def test_connection_request_forwards_the_exact_upstream_signature(tmp_path):
    detail = _detail(tmp_path)

    request = connection_request(detail)

    assert request.kind == request.plot_type == "connection"
    assert request.upstream == "emrisearch.plotting.connection.connection"
    assert set(request.kwargs) == {
        "f",
        "a",
        "b",
        "t_range",
        "n",
        "space",
        "labels",
        "ylabel",
        "title",
        "progress",
    }
    assert request.kwargs["f"] is None
    assert request.kwargs["a"] == tuple(detail.param_space.truth_search)
    assert request.kwargs["b"] == tuple(detail.best.search_coordinates)
    assert request.kwargs["t_range"] == (-0.3, 1.3)
    assert request.kwargs["n"] == 81
    assert request.kwargs["space"] is detail.param_space
    assert request.kwargs["labels"] == ("injection", "recovered")
    assert request.kwargs["ylabel"] == "statistic"
    assert request.kwargs["title"] is None
    assert request.kwargs["progress"] is False
    assert request.theme is PlotTheme.DEFAULT
    assert request.truth is None
    assert request.options == {"progress": False}


def test_connection_request_custom_values_and_search_coordinate_endpoints(tmp_path):
    detail = _detail(tmp_path)

    request = connection_request(
        detail,
        n=7,
        t_range=[0, 1],
        ylabel="log likelihood",
        progress=True,
    )

    assert request.kwargs["n"] == 7
    assert request.kwargs["t_range"] == (0.0, 1.0)
    assert request.kwargs["ylabel"] == "log likelihood"
    assert request.kwargs["progress"] is True
    assert request.kwargs["a"] == tuple(detail.param_space.truth_search)
    assert request.kwargs["b"] == tuple(detail.best.search_coordinates)

    with pytest.raises(ValueError):
        connection_request(detail, n=0)
    with pytest.raises(ValueError):
        connection_request(detail, t_range=(1, 1))
