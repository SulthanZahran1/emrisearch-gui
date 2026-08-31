"""Local-first, heavy-stack-free, numpy-only emrisearch data layer.

This package reads upstream run directories and produces immutable-ish
application data for the results explorer.  It intentionally does not require
FastAPI, matplotlib, corner, PARIS, or the EMRI waveform stack; the optional
upstream result loader is attempted only by :mod:`emri.detail`.
"""

from .config_builder import (
    Artifact,
    ArtifactBundle,
    ArtifactConflictError,
    ArtifactPathError,
    ConfigValidationError,
    EMRICConfig,
    build_artifacts,
    canonical_config,
    default_config,
    generate_config_artifacts,
    normalize_config,
    write_artifacts,
)
from .detail import (
    LightParamSpace,
    LightRunResult,
    ParamSpace,
    RunResult,
    best_per_process,
    build_detail,
    load_result,
    n_sigma_to_contain,
)
from .fixtures import make_legacy, make_legacy_run, make_manifest_run, make_run_chain
from .lineage import chain_of
from .plots import connection_request, corner_request
from .root import (
    add_run,
    add_run_path,
    get_run_roots,
    load_config,
    register_run,
    register_run_path,
    resolve_run_root,
    resolve_run_roots,
    save_config,
)
from .scan import get_scan_warnings, scan_run_root
from .summary import summarize_run
from .types import (
    UNSET,
    BestPerProcessTable,
    BestPoint,
    BestPointDimension,
    ConnectionPlotRequest,
    CornerPlotRequest,
    Diagnostics,
    ManifestDetails,
    ManifestGroups,
    ManifestView,
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
    Theme,
)

__all__ = [
    # core views and diagnostics
    "build_detail", "load_result", "LightRunResult", "LightParamSpace",
    "RunResult", "ParamSpace", "n_sigma_to_contain", "best_per_process", "summarize_run",
    "scan_run_root", "get_scan_warnings", "chain_of",
    # root/config
    "load_config", "save_config", "resolve_run_root", "resolve_run_roots",
    "get_run_roots", "register_run_path", "register_run", "add_run",
    "add_run_path",
    # plot requests
    "corner_request", "connection_request",
    # config artifact generation
    "Artifact", "ArtifactBundle", "ArtifactConflictError", "ArtifactPathError",
    "ConfigValidationError", "EMRICConfig", "build_artifacts", "canonical_config",
    "default_config", "generate_config_artifacts", "normalize_config",
    "write_artifacts",
    # fixtures
    "make_manifest_run", "make_legacy_run", "make_legacy", "make_run_chain",
    # display/data contracts
    "UNSET", "PlotTheme", "Theme", "RunSummary", "SearchDimension",
    "SearchSpaceTable", "ManifestDetails", "ManifestView", "ManifestGroups",
    "BestPointDimension", "BestPoint", "NSigmaRow", "NSigmaTable",
    "ProcessBest", "BestPerProcessTable", "Diagnostics", "SampleCounts",
    "RunDetail", "PlotRequest", "CornerPlotRequest", "ConnectionPlotRequest",
]
# Keep this package-level list explicit: it is the stable public API and avoids
# accidentally exporting implementation imports from a wildcard namespace.
