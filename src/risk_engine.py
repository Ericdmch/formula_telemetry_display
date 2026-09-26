from dataclasses import dataclass

from config import Config
from src.features import SafetyFeatures
from src.model import ModelResult
from src.sensor_fusion import FusedFeatures


# Prototype/demo severity ordering, least to most severe. This is a demo
# escalation ladder, not an official FIA rulebook mapping.
FLAG_SEVERITY = {
    "GREEN": 0,
    "YELLOW": 1,
    "DOUBLE_YELLOW": 2,
    "VSC": 3,
    "SAFETY_CAR": 4,
    "RED_RECOMMENDED": 5,
}

# Flags at or above this severity latch: once the pipeline recommends one, it
# holds it instead of downgrading later in the same run (prototype behavior).
LATCH_MIN_FLAG = "VSC"


@dataclass(frozen=True)
class FlagDecision:
    flag: str
    rule_id: str


def severity(flag: str | None) -> int:
    return FLAG_SEVERITY.get(flag or "", 0)


def latch_flag(previous_flag: str, new_flag: str) -> str:
    """Hold an escalated recommendation instead of downgrading it.

    VSC and above never step back down within a run (no red -> yellow); below
    the latch threshold the fresh recommendation is used as-is.
    """
    if severity(new_flag) >= severity(previous_flag):
        return new_flag
    if severity(previous_flag) >= severity(LATCH_MIN_FLAG):
        return previous_flag
    return new_flag


def recommend_flag(
    features: SafetyFeatures | FusedFeatures, model_result: ModelResult, config: Config
) -> FlagDecision:
    stopped = features.stationary_time_s >= config.stopped_time_s
    # Prototype/demo: a debris hazard reported on the racing line (marshal /
    # race-control report) with the field circulating is a VSC situation even
    # when no car has stopped — telemetry alone cannot see static debris.
    debris_vsc = (
        isinstance(features, FusedFeatures) and features.debris_reported is True
    )
    if not stopped and not features.multiple_cars_affected and not debris_vsc:
        return FlagDecision(
            "GREEN",
            "UNCONFIRMED_CANDIDATE" if features.incident_detected else "NO_INCIDENT",
        )

    if isinstance(features, FusedFeatures):
        if (stopped and features.recovery_vehicle_present is True
                and features.track_wet is True
                and features.visibility_condition == "POOR"):
            return FlagDecision("RED_RECOMMENDED", "RECOVERY_WET_POOR_VISIBILITY")
        if (stopped and features.vision_vehicle_on_track is True
                and features.vision_confidence is not None
                and features.vision_confidence >= config.vision_min_confidence
                and features.vision_track_blockage_fraction is not None
                and features.vision_track_blockage_fraction >= config.vision_blockage_threshold):
            return FlagDecision("RED_RECOMMENDED", "VISUAL_BLOCKAGE_WITH_STOP")

    score = model_result.risk_score
    close_fast_traffic = (
        features.closest_approaching_car_id is not None
        and features.closest_car_distance_m <= config.close_distance_m
        and features.closing_speed_kmh >= config.high_closing_speed_kmh
    )
    # Deterministic geometric evidence overrides the model band: a stopped car
    # on the racing line with fast traffic closing in is a safety-car call no
    # matter what the statistical score says.
    if (
        stopped
        and features.on_racing_line
        and features.stationary_time_s >= 4.0
        and close_fast_traffic
    ):
        return FlagDecision("SAFETY_CAR", "ON_LINE_CLOSE_FAST_TRAFFIC")
    if features.multiple_cars_affected and score >= 0.60:
        return FlagDecision("SAFETY_CAR", "MULTI_CAR_HIGH_RISK")

    if debris_vsc:
        return FlagDecision("VSC", "DEBRIS_REPORTED_ON_TRACK")

    if score >= config.red_risk_threshold:
        decision = FlagDecision("RED_RECOMMENDED", "MODEL_RISK_RED")
    elif score >= config.yellow_risk_threshold:
        decision = FlagDecision("YELLOW", "MODEL_RISK_YELLOW")
    else:
        decision = FlagDecision("GREEN", "MODEL_RISK_LOW")

    if (
        decision.flag == "GREEN"
        and stopped
        and features.closest_approaching_car_id is not None
        and features.closest_car_distance_m <= 200
        and features.closing_speed_kmh >= 80
    ):
        return FlagDecision("VSC", "STOPPED_WITH_TRAFFIC")
    if decision.flag == "GREEN" and stopped and features.on_racing_line:
        return FlagDecision("DOUBLE_YELLOW", "STOPPED_ON_LINE")
    return decision
