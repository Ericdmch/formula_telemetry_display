"""Local, source-labelled historical replays using the normal SafetyPipeline."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

import pandas as pd

from config import Config
from src.pipeline import AnalysisResult, SafetyPipeline
from src.sensor_fusion import EnvironmentalContext, VisualFeatures
from src.speed_profile import SpeedProfile, build_speed_profile
from src.telemetry import load_telemetry
from src.track import load_track


SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "data" / "scenarios"
QUALITY_VALUES = {
    "REAL_TELEMETRY_WITH_DERIVED_FEATURES",
    "HISTORICALLY_GROUNDED_RECONSTRUCTION",
}
ORIGIN_VALUES = {"REAL", "DERIVED", "RECONSTRUCTED", "SIMULATED"}


@dataclass(frozen=True)
class HistoricalScenario:
    path: Path
    metadata: dict
    frames: list[pd.DataFrame]
    track_path: Path

    @property
    def scenario_id(self) -> str:
        return self.metadata["scenario_id"]

    @property
    def incident_offset_s(self) -> float:
        return float(self.metadata["incident_offset_s"])

    def relative_time(self, timestamp_s: float) -> float:
        return timestamp_s - self.incident_offset_s

    def actual_state(self, relative_time_s: float) -> str:
        state = "GREEN / SESSION RUNNING"
        if relative_time_s >= 0 and any(a["relative_time_s"] is None for a in self.metadata["actual_control_actions"]):
            state = "Documented control sequence — exact timing unavailable"
        for action in self.metadata["actual_control_actions"]:
            when = action["relative_time_s"]
            if when is not None and when <= relative_time_s:
                if action["action"] in ("YELLOW", "DOUBLE YELLOW"):
                    if state not in ("VSC", "SAFETY CAR", "RED FLAG"):
                        state = action["action"] + " (LOCAL MESSAGE)"
                else:
                    state = action["action"]
        return state

    def speed_profile(self) -> SpeedProfile | None:
        """Normal speed profile for this scenario, built from its telemetry."""
        return build_speed_profile(self.frames, load_track(self.track_path))

    def replay(self, config: Config | None = None) -> list[AnalysisResult]:
        track = load_track(self.track_path)
        pipeline = SafetyPipeline(
            config, track=track, speed_profile=build_speed_profile(self.frames, track)
        )
        return [self.update_pipeline(pipeline, frame) for frame in self.frames]

    def environment_at(self, frame: pd.DataFrame) -> EnvironmentalContext | None:
        weather = self.metadata.get("weather_context") or {}
        track = self.metadata.get("track_context") or {}
        if not weather and not track:
            return None
        focus_id = self.metadata["incident_cars"][0]
        focus = frame[frame["car_id"] == focus_id]
        if focus.empty:
            return None
        relative = self.relative_time(float(frame["timestamp_s"].iloc[0]))
        recovery = None
        recovery_quality = weather.get("quality")
        debris = None
        debris_quality = None
        for event in self.metadata.get("context_events", []):
            if event["event"] == "Recovery vehicle present" and relative >= event["relative_time_s"]:
                recovery = True
                recovery_quality = event["quality"]
            if event["event"] == "Debris reported on track" and relative >= event["relative_time_s"]:
                debris = True
                debris_quality = event["quality"]
        wet = weather.get("track_wet")
        if wet is None and weather.get("state") == "wet":
            wet = True
        return EnvironmentalContext(
            sector=int(focus.iloc[0]["sector"]), track_wet=wet,
            visibility_condition=weather.get("visibility_condition"),
            recovery_vehicle_present=recovery,
            debris_reported=debris,
            source=weather.get("source") or track.get("source"), quality=recovery_quality or debris_quality,
        )

    def visual_at(self, frame: pd.DataFrame) -> VisualFeatures | None:
        path = self.path / "visual_features.json"
        if not path.is_file():
            return None
        raw = json.loads(path.read_text())
        relative = self.relative_time(float(frame["timestamp_s"].iloc[0]))
        if relative < raw["available_at_relative_s"]:
            return None
        return VisualFeatures(**raw["features"])

    def weather_at(self, relative_time_s: float) -> dict:
        path = self.path / "weather.csv"
        if not path.is_file():
            return self.metadata.get("weather_context", {})
        weather = pd.read_csv(path)
        available = weather[weather["relative_time_s"] <= relative_time_s]
        if available.empty:
            return self.metadata.get("weather_context", {})
        row = available.iloc[-1]
        return {
            "air_temperature_c": row.get("AirTemp"),
            "track_temperature_c": row.get("TrackTemp"),
            "humidity_pct": row.get("Humidity"),
            "rainfall": row.get("Rainfall"),
            "wind_speed": row.get("WindSpeed"),
            "wind_direction_deg": row.get("WindDirection"),
            "source_time_utc": row.get("source_time_utc"),
            "source": "FASTF1_WEATHER",
            "quality": "REAL_SAMPLE_AS_OF_REPLAY_TIME",
        }

    def update_pipeline(self, pipeline: SafetyPipeline, frame: pd.DataFrame,
                        visual_override: VisualFeatures | None = None) -> AnalysisResult:
        visual = visual_override if visual_override is not None else self.visual_at(frame)
        return pipeline.update(frame, environment=self.environment_at(frame), visual=visual)


def scenario_ids(root: Path = SCENARIO_ROOT) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if (path / "scenario.json").is_file())


def load_scenario(scenario_id: str, root: Path = SCENARIO_ROOT) -> HistoricalScenario:
    if not re.fullmatch(r"[a-z0-9_]+", scenario_id):
        raise ValueError("invalid scenario id")
    path = root / scenario_id
    cache_metadata = path / "scenario-cache.json"
    telemetry_path = path / "telemetry.csv"
    measured_available = (telemetry_path.is_file() and cache_metadata.is_file()
                          and (path / "track.json").is_file())
    metadata_path = cache_metadata if measured_available else path / "scenario.json"
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("scenario_id") != scenario_id:
        raise ValueError("scenario id does not match directory")
    for key in ("title", "season", "event", "session", "description", "incident_cars",
                "data_quality", "incident_offset_s", "actual_control_actions", "field_provenance"):
        if key not in metadata:
            raise ValueError(f"missing scenario field: {key}")
    if metadata["data_quality"] not in QUALITY_VALUES:
        raise ValueError("invalid data quality")
    if not metadata["incident_cars"] or not isinstance(metadata["incident_cars"], list):
        raise ValueError("incident cars required")
    if not isinstance(metadata["field_provenance"], dict) or any(
        value not in ORIGIN_VALUES for value in metadata["field_provenance"].values()
    ):
        raise ValueError("invalid field provenance")
    actions = metadata["actual_control_actions"]
    timed = []
    for action in actions:
        if not {"action", "relative_time_s", "source", "timing_quality"} <= action.keys():
            raise ValueError("incomplete actual control action")
        if action["action"] not in {"YELLOW", "DOUBLE YELLOW", "VSC", "SAFETY CAR", "RED FLAG"}:
            raise ValueError("unsupported actual control action")
        if not action["source"] or not action["timing_quality"]:
            raise ValueError("control action source and timing quality required")
        if action["relative_time_s"] is not None:
            when = float(action["relative_time_s"])
            if not math.isfinite(when):
                raise ValueError("nonfinite actual control time")
            timed.append(when)
    if timed != sorted(timed):
        raise ValueError("actual control actions out of time order")

    if not measured_available:
        telemetry_path = path / "reconstruction.csv"
    frames = load_telemetry(telemetry_path)
    first = float(frames[0]["timestamp_s"].iloc[0])
    last = float(frames[-1]["timestamp_s"].iloc[0])
    offset = float(metadata["incident_offset_s"])
    if not math.isfinite(offset) or not first <= offset <= last:
        raise ValueError("incident T=0 outside replay")
    if not any(abs(float(f["timestamp_s"].iloc[0]) - offset) < 1e-6 for f in frames):
        raise ValueError("incident T=0 is not a sample")
    if any("relative_time_s" not in f or not (abs(f["relative_time_s"] - (f["timestamp_s"] - offset)) < 1e-6).all() for f in frames):
        raise ValueError("relative timeline does not match incident offset")
    origins = {"speed_origin", "position_origin", "accel_origin"}
    if any(not origins <= set(f.columns) for f in frames):
        raise ValueError("motion origin columns required")
    if metadata["data_quality"] == "HISTORICALLY_GROUNDED_RECONSTRUCTION":
        if any(not (f[["speed_origin", "position_origin", "accel_origin"]] == "SIMULATED").all().all() for f in frames):
            raise ValueError("reconstruction contains unlabelled motion")
    else:
        if any(not (f["speed_origin"] == "REAL").all() or not (f["position_origin"] == "DERIVED").all() or not (f["accel_origin"] == "DERIVED").all() for f in frames):
            raise ValueError("measured cache contains inconsistent motion origins")
    local_track = path / "track.json"
    track_path = local_track if local_track.is_file() else Config().track_path
    return HistoricalScenario(path, metadata, frames, track_path)
