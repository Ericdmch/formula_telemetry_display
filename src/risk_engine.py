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
    stopped = (
        features.speed_kmh <= config.stopped_speed_kmh
        or features.stationary_time_s >= config.stopped_time_s
    )
    street_circuit = (
        isinstance(features, FusedFeatures)
        and (features.track_type or "").upper() == "STREET_CIRCUIT"
    )
    no_runoff = (
        isinstance(features, FusedFeatures)
        and features.runoff_available is False
    )
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
        # RED is reserved for corroborated operational evidence below. A
        # model severity estimate alone cannot establish that the circuit is
        # unsafe to continue on.
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
        if stopped and street_circuit and features.multiple_cars_affected:
            return FlagDecision("RED_RECOMMENDED", "MULTI_CAR_STREET_CIRCUIT")
        if (
            stopped
            and street_circuit
            and no_runoff
            and features.stationary_time_s >= config.red_stationary_time_s
        ):
            return FlagDecision("RED_RECOMMENDED", "PROLONGED_STREET_CIRCUIT_STOP")

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
        and features.stationary_time_s >= config.safety_car_stationary_s
        and close_fast_traffic
    ):
        rule_id = (
            "ON_LINE_CLOSE_FAST_TRAFFIC"
            if features.on_racing_line
            else "STOPPED_WITH_FAST_TRAFFIC"
        )
        return FlagDecision("SAFETY_CAR", rule_id)
    if features.multiple_cars_affected and score >= config.multi_car_risk_threshold:
        return FlagDecision("SAFETY_CAR", "MULTI_CAR_HIGH_RISK")
    if (
        stopped
        and features.stationary_time_s >= config.safety_car_stationary_s
        and (street_circuit or no_runoff)
    ):
        return FlagDecision("SAFETY_CAR", "STOPPED_IN_HIGH_RISK_LOCATION")

    if debris_vsc:
        return FlagDecision("VSC", "DEBRIS_REPORTED_ON_TRACK")

    if stopped and features.stationary_time_s >= config.vsc_stationary_time_s:
        return FlagDecision("VSC", "SUSTAINED_STOP_VSC")

    if score >= config.high_risk_review_threshold:
        decision = FlagDecision("YELLOW", "MODEL_RISK_HIGH_REVIEW")
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
    if decision.flag == "GREEN" and stopped:
        return FlagDecision("YELLOW", "STOPPED_CAR_YELLOW")
    return decision
