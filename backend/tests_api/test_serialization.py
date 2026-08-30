"""JSON-boundary tests for the backend display dataclasses."""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np

from backend.api.serialization import (
    NumpyJSONEncoder,
    serialize_run_detail,
    to_jsonable,
)
from backend.emri import (
    BestPerProcessTable,
    BestPoint,
    BestPointDimension,
    Diagnostics,
    ManifestDetails,
    NSigmaRow,
    NSigmaTable,
    ProcessBest,
    RunDetail,
    RunSummary,
    SampleCounts,
)


def test_numpy_scalars_arrays_tuples_paths_and_sentinels_are_native_json():
    value = {
        "float": np.float64(1.25),
        "integer": np.int64(7),
        "boolean": np.bool_(True),
        "array": np.asarray([[np.int64(1), np.float32(2.5)]]),
        "tuple": (np.float64(3.0), Path("nested/file")),
        "path": Path("/tmp/run"),
        "unset": "unset",
        "none": None,
    }

    converted = to_jsonable(value)
    encoded = json.dumps(converted)
    round_trip = json.loads(encoded)

    assert type(converted["float"]) is float
    assert type(converted["integer"]) is int
    assert type(converted["boolean"]) is bool
    assert converted["array"] == [[1, 2.5]]
    assert converted["tuple"] == [3.0, "nested/file"]
    assert converted["path"] == "/tmp/run"
    assert converted["unset"] == "unset"
    assert converted["none"] is None
    assert round_trip == {
        "float": 1.25,
        "integer": 7,
        "boolean": True,
        "array": [[1, 2.5]],
        "tuple": [3.0, "nested/file"],
        "path": "/tmp/run",
        "unset": "unset",
        "none": None,
    }


def test_numpy_json_encoder_handles_values_directly():
    payload = json.loads(
        json.dumps(
            {"value": np.float32(2.5), "items": np.asarray([1, 2])},
            cls=NumpyJSONEncoder,
        )
    )

    assert payload == {"value": 2.5, "items": [1, 2]}


def test_run_detail_serialization_preserves_dataclass_field_names_and_excludes_live_objects():
    summary = RunSummary(
        id="nested/run",
        path=Path("/tmp/nested/run"),
        kind="from_run",
        statistic="pure",
        ndim=1,
        best_log_density=np.float64(1.5),
        from_run="../parent",
        out=".",
        result_kind="unset",
        warnings=("unset",),
    )
    best_dimension = BestPointDimension(
        name="m1",
        transform="log10",
        search=np.float64(5.5),
        physical=np.float64(316227.766),
        n_sigma=np.float64(0.0),
    )
    best = BestPoint(
        log_density=np.float64(1.5),
        dimensions=(best_dimension,),
        search_coordinates=(np.float64(5.5),),
        physical_coordinates=(np.float64(316227.766),),
    )
    diagnostics = Diagnostics(
        n_sigma_to_contain=NSigmaTable(
            rows=(NSigmaRow("m1", 5.5, 5.5, 0.1, 0.0),),
            available=True,
        ),
        best_per_process=BestPerProcessTable(
            rows=(ProcessBest(0, log_density=np.float64(1.5)),),
            spread=np.float64(0.0),
            merged=True,
            available=True,
        ),
    )
    detail = RunDetail(
        summary=summary,
        path=Path("/tmp/nested/run"),
        manifest={"space": {"free": ("m1",)}, "unset": "unset"},
        manifest_groups=ManifestDetails(),
        best=best,
        diagnostics=diagnostics,
        samples=SampleCounts(n_samples=2, n_finite=2),
        result=object(),
        param_space=object(),
        warnings=("warning",),
    )

    payload = serialize_run_detail(detail)
    round_trip = json.loads(json.dumps(payload))

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
    assert "result" not in payload
    assert "param_space" not in payload
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
    assert set(payload["best"]) == {
        "log_density",
        "dimensions",
        "search_coordinates",
        "physical_coordinates",
    }
    assert set(payload["best"]["dimensions"][0]) == {
        "name",
        "transform",
        "search",
        "physical",
        "n_sigma",
    }
    assert set(payload["diagnostics"]) == {"n_sigma_to_contain", "best_per_process"}
    assert set(payload["samples"]) == {"n_samples", "n_finite"}
    assert round_trip["summary"]["path"] == "/tmp/nested/run"
    assert round_trip["best"]["dimensions"][0]["n_sigma"] == 0.0
    assert round_trip["manifest"]["unset"] == "unset"
