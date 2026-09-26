"""Typed contextual evidence layered on the stable seven-field telemetry model vector."""

from dataclasses import asdict, dataclass

from src.features import SafetyFeatures


@dataclass(frozen=True)
class EnvironmentalContext:
    sector: int
    track_type: str | None = None
    corner_type: str | None = None
    runoff_available: bool | None = None
    rain_intensity: float | None = None
    track_wet: bool | None = None
    visibility_m: float | None = None
    temperature_c: float | None = None
    visibility_condition: str | None = None
    recovery_vehicle_present: bool | None = None
    debris_reported: bool | None = None
    source: str | None = None
    quality: str | None = None


@dataclass(frozen=True)
class VisualFeatures:
    vehicle_stopped_visible: bool | None = None
    vehicle_on_track: bool | None = None
    track_blockage_fraction: float | None = None
    multiple_vehicles_involved: bool | None = None
    debris_visible: bool | None = None
    smoke_visible: bool | None = None
    fire_visible: bool | None = None
    wet_surface_visible: bool | None = None
    poor_visibility_visible: bool | None = None
    visual_severity: float | None = None
    confidence: float = 0.0
    source: str = "cached"

    def __post_init__(self) -> None:
        if self.source not in ("provider", "cached", "manual"):
            raise ValueError("invalid visual source")
        if not 0 <= self.confidence <= 1:
            raise ValueError("visual confidence outside [0,1]")
        if self.track_blockage_fraction is not None and not 0 <= self.track_blockage_fraction <= 1:
            raise ValueError("visual blockage outside [0,1]")


@dataclass(frozen=True)
class FusedFeatures(SafetyFeatures):
    track_wet: bool | None = None
    visibility_condition: str | None = None
    recovery_vehicle_present: bool | None = None
    debris_reported: bool | None = None
    context_source: str | None = None
    context_quality: str | None = None
    vision_vehicle_on_track: bool | None = None
    vision_track_blockage_fraction: float | None = None
    vision_debris_visible: bool | None = None
    vision_multiple_vehicles: bool | None = None
    vision_confidence: float | None = None
    vision_source: str | None = None

    def context_dict(self) -> dict:
        return {key: getattr(self, key) for key in (
            "track_wet", "visibility_condition", "recovery_vehicle_present",
            "debris_reported",
            "context_source", "context_quality", "vision_vehicle_on_track",
            "vision_track_blockage_fraction", "vision_debris_visible",
            "vision_multiple_vehicles", "vision_confidence", "vision_source",
        )}


def fuse_features(telemetry: SafetyFeatures,
                  environment: EnvironmentalContext | None = None,
                  visual: VisualFeatures | None = None) -> FusedFeatures:
    if environment is not None and environment.sector != telemetry.sector:
        environment = None
    if visual is not None:
        if not 0 <= visual.confidence <= 1:
            raise ValueError("visual confidence outside [0,1]")
        if visual.track_blockage_fraction is not None and not 0 <= visual.track_blockage_fraction <= 1:
            raise ValueError("visual blockage outside [0,1]")
    return FusedFeatures(
        **asdict(telemetry),
        track_wet=environment.track_wet if environment else None,
        visibility_condition=environment.visibility_condition if environment else None,
        recovery_vehicle_present=environment.recovery_vehicle_present if environment else None,
        debris_reported=environment.debris_reported if environment else None,
        context_source=environment.source if environment else None,
        context_quality=environment.quality if environment else None,
        vision_vehicle_on_track=visual.vehicle_on_track if visual else None,
        vision_track_blockage_fraction=visual.track_blockage_fraction if visual else None,
        vision_debris_visible=visual.debris_visible if visual else None,
        vision_multiple_vehicles=visual.multiple_vehicles_involved if visual else None,
        vision_confidence=visual.confidence if visual else None,
        vision_source=visual.source if visual else None,
    )
