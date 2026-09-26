from dataclasses import dataclass

from config import Config
from src.features import SafetyFeatures
from src.model import ModelResult


@dataclass(frozen=True)
class FlagDecision:
    flag: str
    rule_id: str


def recommend_flag(
    features: SafetyFeatures, model_result: ModelResult, config: Config
) -> FlagDecision:
    if not features.incident_detected:
        return FlagDecision("GREEN", "NO_INCIDENT")

    score = model_result.risk_score
    if score >= config.red_risk_threshold:
        decision = FlagDecision("RED_RECOMMENDED", "MODEL_RISK_RED")
    elif score >= config.yellow_risk_threshold:
        decision = FlagDecision("YELLOW", "MODEL_RISK_YELLOW")
    else:
        decision = FlagDecision("GREEN", "MODEL_RISK_LOW")

    stopped = features.stationary_time_s >= config.stopped_time_s
    close_fast_traffic = (
        features.closest_approaching_car_id is not None
        and features.closest_car_distance_m <= config.close_distance_m
        and features.closing_speed_kmh >= config.high_closing_speed_kmh
    )
    if (
        stopped
        and features.on_racing_line
        and features.stationary_time_s >= 4.0
        and close_fast_traffic
    ):
        return FlagDecision("RED_RECOMMENDED", "ON_LINE_CLOSE_FAST_TRAFFIC")
    if features.multiple_cars_affected and score >= 0.60:
        return FlagDecision("RED_RECOMMENDED", "MULTI_CAR_HIGH_RISK")
    if (
        decision.flag == "RED_RECOMMENDED"
        and not stopped
        and features.speed_kmh >= 30
        and not features.multiple_cars_affected
    ):
        return FlagDecision("YELLOW", "SEVERE_DECEL_CAP")
    if decision.flag == "GREEN" and stopped and features.on_racing_line:
        return FlagDecision("YELLOW", "STOPPED_ON_LINE")
    if (
        decision.flag == "GREEN"
        and stopped
        and features.closest_approaching_car_id is not None
        and features.closest_car_distance_m <= 200
        and features.closing_speed_kmh >= 80
    ):
        return FlagDecision("YELLOW", "STOPPED_WITH_TRAFFIC")
    return decision
