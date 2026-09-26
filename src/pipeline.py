from dataclasses import asdict, dataclass

import pandas as pd

from config import Config
from src.explain import build_reasons
from src.features import extract_features
from src.incident_detection import IncidentDetector
from src.model import RiskEstimator
from src.risk_engine import latch_flag, recommend_flag, severity
from src.sensor_fusion import EnvironmentalContext, VisualFeatures, fuse_features
from src.speed_profile import SpeedProfile
from src.track import Track, demo_track_fallback, load_track


@dataclass(frozen=True)
class AnalysisResult:
    timestamp_s: float
    status: str
    flag: str | None
    severity: str
    risk_score: float
    probabilities: dict[str, float]
    model_source: str
    rule_id: str | None
    incident: dict | None
    closest_approaching_car: dict | None
    features: dict | None
    reasons: list[str]
    vehicles: list[dict]
    quality_notes: list[str]
    context_evidence: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class SafetyPipeline:
    def __init__(
        self,
        config: Config | None = None,
        track: Track | None = None,
        estimator: RiskEstimator | None = None,
        speed_profile: SpeedProfile | None = None,
    ):
        self.config = config or Config()
        self.speed_profile = speed_profile
        self.track_quality_note: str | None = None
        if track is not None:
            self.track = track
        else:
            try:
                self.track = load_track(self.config.track_path)
            except (OSError, ValueError, KeyError, TypeError):
                self.track = demo_track_fallback()
                self.track_quality_note = (
                    "Track asset unavailable; using built-in demo geometry"
                )
        self.estimator = estimator or RiskEstimator.load_or_fallback(
            self.config.model_path
        )
        self.detector = IncidentDetector(self.config, self.speed_profile)
        self.last_timestamp_s: float | None = None
        # Prototype latch: once VSC or above is recommended, hold it instead of
        # downgrading later in the same run.
        self._latched_flag: str = "GREEN"
        self._latched_rule_id: str | None = None

    def reset(self) -> None:
        """Clear per-run state: detector histories, frame clock, flag latch."""
        self.detector = IncidentDetector(self.config, self.speed_profile)
        self.last_timestamp_s = None
        self._latched_flag = "GREEN"
        self._latched_rule_id = None

    def update(self, frame: pd.DataFrame,
               environment: EnvironmentalContext | None = None,
               visual: VisualFeatures | None = None) -> AnalysisResult:
        if frame.empty:
            timestamp = (
                0.0 if self.last_timestamp_s is None else self.last_timestamp_s
            )
            return self._unavailable(timestamp, "No vehicle samples in frame")
        timestamp = float(frame["timestamp_s"].iloc[0])
        if self.last_timestamp_s is not None and timestamp <= self.last_timestamp_s:
            raise ValueError("frames must arrive in strictly increasing time order")
        gap = (
            0.0
            if self.last_timestamp_s is None
            else timestamp - self.last_timestamp_s
        )
        self.last_timestamp_s = timestamp
        detected = self.detector.update(frame, self.track)
        if gap > self.config.data_unavailable_gap_s:
            return self._unavailable(
                timestamp, f"Telemetry gap of {gap:.1f} s exceeded 1.0 s"
            )

        candidates = []
        for car in detected:
            features = fuse_features(extract_features(car), environment, visual)
            model_result = self.estimator.predict(features)
            decision = recommend_flag(features, model_result, self.config)
            candidates.append((features, model_result, decision))
        features, model_result, decision = max(
            candidates,
            key=lambda item: (
                severity(item[2].flag),
                round(item[1].risk_score, 6),
                -item[0].car_id,
            ),
        )
        held_flag = latch_flag(self._latched_flag, decision.flag)
        if severity(held_flag) > severity(decision.flag):
            # Latched: keep the earlier escalation and its rule.
            flag = self._latched_flag
            rule_id = self._latched_rule_id
        else:
            flag = decision.flag
            rule_id = decision.rule_id
            self._latched_flag = flag
            self._latched_rule_id = rule_id
        incident = None
        approaching = None
        model_features = None
        if features.incident_detected:
            incident = {
                "car_id": features.car_id,
                "sector": features.sector,
                "speed_kmh": features.speed_kmh,
                "stationary_time_s": features.stationary_time_s,
                "peak_decel_g": features.peak_decel_g,
                "x_m": features.x_m,
                "y_m": features.y_m,
            }
            model_features = features.model_vector()
            if features.closest_approaching_car_id is not None:
                approaching = {
                    "car_id": features.closest_approaching_car_id,
                    "distance_m": features.closest_car_distance_m,
                    "speed_kmh": features.closest_approaching_car_speed_kmh,
                    "closing_speed_kmh": features.closing_speed_kmh,
                }
        vehicles = [
            {
                "car_id": car.car_id,
                "x_m": car.x_m,
                "y_m": car.y_m,
                "speed_kmh": car.speed_kmh,
                "sector": car.sector,
            }
            for car in detected
        ]
        quality_notes = [self.track_quality_note] if self.track_quality_note else []
        for row in frame.itertuples(index=False):
            if getattr(row, "speed_imputed", False):
                quality_notes.append(f"Car #{row.car_id} speed interpolated")
            if getattr(row, "accel_imputed", False):
                quality_notes.append(f"Car #{row.car_id} acceleration interpolated")
        reasons = build_reasons(features, decision, self.config)
        if severity(held_flag) > severity(decision.flag):
            reasons.append(
                f"Recommendation held at {flag.replace('_', ' ')}: no downgrade "
                "after escalation (prototype latch)"
            )
        return AnalysisResult(
            timestamp_s=timestamp,
            status="OK",
            flag=flag,
            severity=model_result.predicted_class,
            risk_score=model_result.risk_score,
            probabilities=model_result.probabilities,
            model_source=model_result.model_source,
            rule_id=rule_id,
            incident=incident,
            closest_approaching_car=approaching,
            features=model_features,
            reasons=reasons,
            vehicles=vehicles,
            quality_notes=quality_notes,
            context_evidence=features.context_dict() if features.incident_detected else None,
        )

    def _unavailable(self, timestamp: float, reason: str) -> AnalysisResult:
        return AnalysisResult(
            timestamp_s=timestamp,
            status="DATA_UNAVAILABLE",
            flag=None,
            severity="UNKNOWN",
            risk_score=0.0,
            probabilities={
                "NORMAL": 0.0,
                "MODERATE_RISK": 0.0,
                "HIGH_RISK": 0.0,
            },
            model_source=self.estimator.model_source,
            rule_id=None,
            incident=None,
            closest_approaching_car=None,
            features=None,
            reasons=[],
            vehicles=[],
            quality_notes=(
                [reason, self.track_quality_note]
                if self.track_quality_note
                else [reason]
            ),
        )
