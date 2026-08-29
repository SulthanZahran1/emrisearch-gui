"""Public data contracts for the local-first emrisearch results explorer.

The types in this module deliberately contain display-ready, serialisable
values rather than web-framework models.  The data layer can therefore be
used by a future API, a command-line inspector, or a notebook without pulling
in FastAPI or the upstream waveform stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


#: Display sentinel used whenever a manifest or a diagnostic does not provide
#: a value.  Raw manifests remain untouched; the sentinel is for the view.
UNSET = "unset"


class PlotTheme(str, Enum):
    """Matplotlib theme hints understood by the future PNG endpoint."""

    DEFAULT = "default"
    DARK = "dark"
    PAPER = "paper"


# Friendly aliases for callers that prefer the shorter vocabulary.
Theme = PlotTheme


@dataclass(frozen=True)
class RunSummary:
    """The inexpensive row shown in the explorer's run rail.

    ``kind`` is the seeding kind for manifest-backed runs (``internal_lhs``,
    ``lhs``, ``fixed_point`` or ``from_run``).  A run with no manifest is
    intentionally reported as ``legacy``.  ``result_kind`` is separate because
    a manifest-only scan must not open the state pickle merely to discover its
    storage shape.
    """

    id: str
    path: str
    kind: str = UNSET
    statistic: str = UNSET
    ndim: Optional[int] = None
    best_log_density: Optional[float] = None
    from_run: Optional[str] = None
    out: Optional[str] = None
    result_kind: str = UNSET
    warnings: Tuple[str, ...] = ()

    @property
    def name(self) -> str:
        """The display name; currently the run id (which may be nested)."""
        return self.id

    @property
    def run_id(self) -> str:
        return self.id

    @property
    def seeding_kind(self) -> str:
        return self.kind

    @property
    def seeding(self) -> str:
        return self.kind

    @property
    def dims(self) -> Optional[int]:
        return self.ndim

    @property
    def statistic_name(self) -> str:
        return self.statistic

    @property
    def best_ld(self) -> Optional[float]:
        return self.best_log_density

    @property
    def best_logdensity(self) -> Optional[float]:
        return self.best_log_density


@dataclass(frozen=True)
class SearchDimension:
    """One row of the search-space table.

    ``name`` is the canonical physical parameter name (for example ``m1``),
    while ``search_coord`` is the sampler-facing name (for example
    ``log10_m1``).  ``lo`` and ``hi`` are always search-coordinate bounds.
    """

    name: str
    transform: str = UNSET
    lo: Any = UNSET
    hi: Any = UNSET
    search_coord: str = UNSET

    @property
    def search_name(self) -> str:
        return self.search_coord

    @property
    def bounds(self) -> Tuple[Any, Any]:
        return self.lo, self.hi


@dataclass(frozen=True)
class SearchSpaceTable:
    """Display representation of ``manifest['space']``."""

    dimensions: Tuple[SearchDimension, ...] = ()
    fixed: Mapping[str, Any] = field(default_factory=dict)
    truth: Mapping[str, Any] = field(default_factory=dict)

    @property
    def free(self) -> Tuple[SearchDimension, ...]:
        return self.dimensions

    @property
    def rows(self) -> Tuple[SearchDimension, ...]:
        return self.dimensions

    @property
    def ndim(self) -> int:
        return len(self.dimensions)

    @property
    def fixed_params(self) -> Mapping[str, Any]:
        return self.fixed


@dataclass(frozen=True)
class ManifestDetails:
    """The grouped manifest view consumed by the accepted prototype IA.

    The raw manifest is kept separately on :class:`RunDetail`; this object
    replaces null/missing display values with :data:`UNSET` and groups the
    ten canonical fields emitted by ``ParisRun.manifest``.  No synthetic raw
    manifest keys are added.
    """

    emrisearch_version: Any = UNSET
    source: Mapping[str, Any] = field(default_factory=dict)
    obs: Mapping[str, Any] = field(default_factory=dict)
    noise: Mapping[str, Any] = field(default_factory=dict)
    modes: Mapping[str, Any] = field(default_factory=dict)
    statistic: Mapping[str, Any] = field(default_factory=dict)
    space: SearchSpaceTable = field(default_factory=SearchSpaceTable)
    sampler: Mapping[str, Any] = field(default_factory=dict)
    seeding: Mapping[str, Any] = field(default_factory=dict)
    out: Any = UNSET
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def search_space(self) -> SearchSpaceTable:
        return self.space

    @property
    def fixed_params(self) -> Mapping[str, Any]:
        return self.space.fixed

    @property
    def version(self) -> Any:
        return self.emrisearch_version

    @property
    def observation_noise_modes(self) -> Mapping[str, Any]:
        """Flattened group helper matching the prototype's label."""
        values = {}
        values.update({f"obs.{k}": v for k, v in self.obs.items()})
        values.update({f"noise.{k}": v for k, v in self.noise.items()})
        values.update({f"modes.{k}": v for k, v in self.modes.items()})
        return values


# Alias names used by a few consumers of the prototype vocabulary.
ManifestView = ManifestDetails
ManifestGroups = ManifestDetails


@dataclass(frozen=True)
class BestPointDimension:
    """One row in the best-point search/physical-coordinate table."""

    name: str
    transform: str
    search: Any = UNSET
    physical: Any = UNSET
    n_sigma: Any = UNSET

    @property
    def search_coord(self) -> Any:
        return self.search

    @property
    def search_name(self) -> str:
        return self.name

    @property
    def physical_coord(self) -> Any:
        return self.physical

    @property
    def sigma(self) -> Any:
        return self.n_sigma


@dataclass(frozen=True)
class BestPoint:
    """Highest-statistic point and its two coordinate representations."""

    log_density: Optional[float] = None
    dimensions: Tuple[BestPointDimension, ...] = ()
    search_coordinates: Tuple[Any, ...] = ()
    physical_coordinates: Tuple[Any, ...] = ()

    @property
    def ld(self) -> Optional[float]:
        return self.log_density

    @property
    def best_log_density(self) -> Optional[float]:
        return self.log_density

    @property
    def search(self) -> Tuple[Any, ...]:
        return self.search_coordinates

    @property
    def search_coords(self) -> Tuple[Any, ...]:
        return self.search_coordinates

    @property
    def physical(self) -> Tuple[Any, ...]:
        return self.physical_coordinates

    @property
    def physical_coords(self) -> Tuple[Any, ...]:
        return self.physical_coordinates

    @property
    def coords(self) -> Tuple[Any, ...]:
        return self.search_coordinates

    @property
    def rows(self) -> Tuple[BestPointDimension, ...]:
        return self.dimensions

    @property
    def search_by_name(self) -> Mapping[str, Any]:
        return {row.name: row.search for row in self.dimensions}

    @property
    def physical_by_name(self) -> Mapping[str, Any]:
        return {row.name: row.physical for row in self.dimensions}


@dataclass(frozen=True)
class NSigmaRow:
    """Per-dimension ``n_sigma_to_contain`` result."""

    name: str
    best: Any = UNSET
    truth: Any = UNSET
    sigma: Any = UNSET
    n_sigma: Any = UNSET

    @property
    def best_search(self) -> Any:
        return self.best

    @property
    def truth_search(self) -> Any:
        return self.truth

    @property
    def value(self) -> Any:
        return self.n_sigma

    @property
    def distance(self) -> Any:
        return self.n_sigma


@dataclass(frozen=True)
class NSigmaTable:
    """Rows and availability state for ``n_sigma_to_contain``."""

    rows: Tuple[NSigmaRow, ...] = ()
    available: bool = True

    @property
    def values(self) -> Tuple[Any, ...]:
        return tuple(row.n_sigma for row in self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


@dataclass(frozen=True)
class ProcessBest:
    """The best point recorded by one PARIS process."""

    process: int
    log_density: Any = UNSET
    search_coordinates: Tuple[Any, ...] = ()
    physical_coordinates: Tuple[Any, ...] = ()

    @property
    def proc(self) -> int:
        return self.process

    @property
    def ld(self) -> Any:
        return self.log_density

    @property
    def best_log_density(self) -> Any:
        return self.log_density

    @property
    def search(self) -> Tuple[Any, ...]:
        return self.search_coordinates

    @property
    def physical(self) -> Tuple[Any, ...]:
        return self.physical_coordinates


@dataclass(frozen=True)
class BestPerProcessTable:
    """Process-best rows plus the prototype's merged/unmerged read."""

    rows: Tuple[ProcessBest, ...] = ()
    spread: Any = UNSET
    merged: Any = UNSET
    available: bool = False

    @property
    def status(self) -> str:
        if self.merged is True:
            return "merged"
        if self.merged is False:
            return "unmerged"
        return UNSET

    @property
    def read(self) -> str:
        return self.status

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


@dataclass(frozen=True)
class Diagnostics:
    """The two GUI-side diagnostic tables."""

    n_sigma_to_contain: NSigmaTable = field(default_factory=NSigmaTable)
    best_per_process: BestPerProcessTable = field(default_factory=BestPerProcessTable)

    @property
    def n_sigma(self) -> NSigmaTable:
        return self.n_sigma_to_contain


@dataclass(frozen=True)
class SampleCounts:
    """Total and finite sample counts shown in the fact strip."""

    n_samples: int = 0
    n_finite: int = 0

    @property
    def total(self) -> int:
        return self.n_samples

    @property
    def finite(self) -> int:
        return self.n_finite


@dataclass(frozen=True)
class RunDetail:
    """Full display model for one run directory."""

    summary: RunSummary
    path: str
    manifest: Mapping[str, Any] = field(default_factory=dict)
    manifest_groups: ManifestDetails = field(default_factory=ManifestDetails)
    best: BestPoint = field(default_factory=BestPoint)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    samples: SampleCounts = field(default_factory=SampleCounts)
    result: Any = None
    param_space: Any = None
    warnings: Tuple[str, ...] = ()

    @property
    def manifest_view(self) -> ManifestDetails:
        return self.manifest_groups

    @property
    def source(self) -> Mapping[str, Any]:
        return self.manifest_groups.source

    @property
    def obs(self) -> Mapping[str, Any]:
        return self.manifest_groups.obs

    @property
    def noise(self) -> Mapping[str, Any]:
        return self.manifest_groups.noise

    @property
    def modes(self) -> Mapping[str, Any]:
        return self.manifest_groups.modes

    @property
    def statistic(self) -> Mapping[str, Any]:
        return self.manifest_groups.statistic

    @property
    def sampler(self) -> Mapping[str, Any]:
        return self.manifest_groups.sampler

    @property
    def seeding(self) -> Mapping[str, Any]:
        return self.manifest_groups.seeding

    @property
    def out(self) -> Any:
        return self.manifest_groups.out

    @property
    def best_point(self) -> BestPoint:
        return self.best

    @property
    def search_space(self) -> SearchSpaceTable:
        return self.manifest_groups.space

    @property
    def n_samples(self) -> int:
        return self.samples.n_samples

    @property
    def n_finite(self) -> int:
        return self.samples.n_finite

    @property
    def ndim(self) -> int:
        return self.search_space.ndim or len(self.best.search_coordinates)

    @property
    def n_sigma_to_contain(self) -> NSigmaTable:
        return self.diagnostics.n_sigma_to_contain

    @property
    def best_per_process(self) -> BestPerProcessTable:
        return self.diagnostics.best_per_process


@dataclass(frozen=True)
class PlotRequest:
    """Pure request envelope for a future server-side plotting endpoint.

    ``kwargs`` are exactly the arguments accepted by the corresponding
    upstream plotting function.  GUI-only controls such as ``truth`` and
    ``theme`` are kept as request metadata and are never silently forwarded to
    an upstream function that does not accept them.
    """

    kind: str
    upstream: str
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    theme: PlotTheme = PlotTheme.DEFAULT
    truth: Optional[bool] = None
    options: Mapping[str, Any] = field(default_factory=dict)

    @property
    def plot_type(self) -> str:
        return self.kind

    @property
    def type(self) -> str:
        return self.kind

    @property
    def target(self) -> str:
        return self.upstream

    @property
    def params(self) -> Mapping[str, Any]:
        return self.kwargs

    @property
    def upstream_kwargs(self) -> Mapping[str, Any]:
        return self.kwargs

    @property
    def render_options(self) -> Mapping[str, Any]:
        result = dict(self.options)
        theme_value = self.theme.value if isinstance(self.theme, PlotTheme) else str(self.theme)
        result.setdefault("theme", theme_value)
        if self.truth is not None:
            result.setdefault("truth", self.truth)
        return result

    def for_upstream(self) -> Mapping[str, Any]:
        """Return only the kwargs safe to pass to the upstream call."""
        return dict(self.kwargs)


# Explicit names make API discovery pleasant while retaining one common
# request shape for the later endpoint.
CornerPlotRequest = PlotRequest
ConnectionPlotRequest = PlotRequest


__all__ = [
    "UNSET", "PlotTheme", "Theme", "RunSummary", "SearchDimension",
    "SearchSpaceTable", "ManifestDetails", "ManifestView", "ManifestGroups",
    "BestPointDimension", "BestPoint", "NSigmaRow", "NSigmaTable",
    "ProcessBest", "BestPerProcessTable", "Diagnostics", "SampleCounts",
    "RunDetail", "PlotRequest", "CornerPlotRequest", "ConnectionPlotRequest",
]
