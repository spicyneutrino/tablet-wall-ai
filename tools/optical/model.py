"""Data shapes shared by the optical inputs, detector, metrics and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RGB = tuple[float, float, float]

MANIFEST_SCHEMA = "tablet-wall-optical-capture/1"
ROIS_SCHEMA = "tablet-wall-optical-rois/1"
EVENTS_SCHEMA = "tablet-wall-optical-events/1"
ANALYSIS_SCHEMA = "tablet-wall-optical-analysis/1"

EVIDENCE_KINDS = ("synthetic", "operator-hardware")
TIMESTAMP_BASES = ("exposure_start", "exposure_centre", "exposure_end")
READOUT_DIRECTIONS = (
    "top-to-bottom",
    "bottom-to-top",
    "left-to-right",
    "right-to-left",
)
PANEL_STATUSES = (
    "observed",
    "missing",
    "wrong-target",
    "partial",
    "ambiguous",
    "unobserved",
)

@dataclass(frozen=True)
class Camera:
    """Camera timing metadata.

    ``resolution`` is the delivered frame size in pixels. ``orientation_deg``
    is the clockwise rotation applied by the camera to the sensor image before
    delivery. The rolling-shutter direction is expressed in sensor readout
    coordinates.
    """

    exposure_us: float
    orientation_deg: int
    width: int
    height: int
    readout_us: float
    readout_direction: str
    readout_measured: bool = True
    model: str | None = None
    gain: str | None = None
    white_balance: str | None = None
    nominal_fps: float | None = None

    @property
    def sensor_width(self) -> int:
        return self.height if self.orientation_deg in (90, 270) else self.width

    @property
    def sensor_height(self) -> int:
        return self.width if self.orientation_deg in (90, 270) else self.height

    @property
    def exposure_s(self) -> float:
        return self.exposure_us / 1_000_000.0

    @property
    def readout_s(self) -> float:
        return self.readout_us / 1_000_000.0


@dataclass(frozen=True)
class Frame:
    index: int
    path: Path | None
    timestamp_s: float


@dataclass(frozen=True)
class Capture:
    capture_id: str
    evidence_kind: str
    camera: Camera
    frames: tuple[Frame, ...]
    dropped_frames: frozenset[int]
    duplicated_frames: frozenset[int]
    timestamp_basis: str
    manifest_path: Path
    clock: dict[str, Any] = field(default_factory=dict)
    panel_scanout: str | None = None
    notes: str | None = None
    warnings: tuple[str, ...] = ()
    video: dict[str, Any] | None = None

    def frame_by_index(self, index: int) -> Frame | None:
        for frame in self.frames:
            if frame.index == index:
                return frame
        return None


@dataclass(frozen=True)
class Region:
    """A sampled region: polygon plus explicit probe points."""

    polygon: tuple[tuple[float, float], ...]
    sample_points: tuple[tuple[float, float], ...]
    sample_radius: int = 1


@dataclass(frozen=True)
class PanelROI:
    panel_id: str
    region: Region
    noise_region: Region | None = None


@dataclass(frozen=True)
class ROISet:
    panels: dict[str, PanelROI]
    source_frame_roi: tuple[int, int, int, int] | None = None
    source_frame_digits: int = 6
    coordinate_space: str = "delivered"


@dataclass(frozen=True)
class Event:
    event_id: str
    reference_frame: int | None
    reference_time_s: float | None
    search_before_s: float
    search_after_s: float
    expected_panels: tuple[str, ...]
    target_rgb: RGB
    target_tolerance: float
    min_target_fraction: float
    steady_state: bool
    source_frame: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class AnalysisConfig:
    """Detection settings. Published gate thresholds are not configurable."""

    baseline_frames: int = 8
    min_baseline_frames: int = 3
    confirm_frames: int = 1
    default_min_target_fraction: float = 0.60
    min_changed_fraction: float = 0.50
    partial_fraction: float = 0.15
    default_target_tolerance: float = 30.0
    min_change: float = 18.0
    max_baseline_noise: float = 20.0
    max_onset_width_s: float = 0.050
    gap_factor: float = 1.5
    p95_limit_ms: float = 100.0
    max_limit_ms: float = 250.0
    minimum_complete_events: int = 100

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_frames": self.baseline_frames,
            "min_baseline_frames": self.min_baseline_frames,
            "confirm_frames": self.confirm_frames,
            "default_min_target_fraction": self.default_min_target_fraction,
            "min_changed_fraction": self.min_changed_fraction,
            "partial_fraction": self.partial_fraction,
            "default_target_tolerance": self.default_target_tolerance,
            "min_change": self.min_change,
            "max_baseline_noise": self.max_baseline_noise,
            "max_onset_width_s": self.max_onset_width_s,
            "gap_factor": self.gap_factor,
            "p95_limit_ms": self.p95_limit_ms,
            "max_limit_ms": self.max_limit_ms,
            "minimum_complete_events": self.minimum_complete_events,
        }


@dataclass
class PanelObservation:
    panel_id: str
    status: str
    onset_lower_s: float | None = None
    onset_point_s: float | None = None
    onset_upper_s: float | None = None
    point_offset_ms: float | None = None
    lower_offset_ms: float | None = None
    upper_offset_ms: float | None = None
    width_ms: float | None = None
    confidence: float = 0.0
    target_fraction: float = 0.0
    changed_fraction: float = 0.0
    noise_rms: float | None = None
    transition_points: int = 0
    readout_offset_min_ms: float | None = None
    readout_offset_max_ms: float | None = None
    onset_frame: int | None = None
    reason: str | None = None


@dataclass
class EventResult:
    event: Event
    reference_frame_index: int | None
    reference_time_s: float | None
    reference_source: str
    window_start_s: float | None
    window_end_s: float | None
    panels: list[PanelObservation]
    status: str
    failure_reason: str | None = None
    skew_point_ms: float | None = None
    skew_lower_ms: float | None = None
    skew_upper_ms: float | None = None
    source_frame: dict[str, Any] | None = None

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            "expected": len(self.event.expected_panels),
            "observed": 0,
            "missing": 0,
            "ambiguous": 0,
            "partial": 0,
            "wrong_target": 0,
            "unobserved": 0,
        }
        for panel in self.panels:
            if panel.status == "wrong-target":
                counts["wrong_target"] += 1
            else:
                counts[panel.status] += 1
        return counts

    @property
    def complete(self) -> bool:
        return (
            self.status == "observed"
            and self.counts["observed"] == self.counts["expected"]
            and self.counts["expected"] > 0
        )


@dataclass
class Analysis:
    capture: Capture
    rois: ROISet
    events: list[EventResult]
    config: AnalysisConfig
    metrics: dict[str, Any]
    unobserved_intervals: list[dict[str, Any]]
    recovery_intervals: list[dict[str, Any]]
    frame_errors: list[dict[str, Any]]
    source_frame_tracking: bool
    video_sync: str
    video_sync_detail: str
    ocr_requested: bool
    started_at: str
    finished_at: str
    timing_source: str
    tool_version: str
