from config import Config
from src.features import SafetyFeatures
from src.risk_engine import FlagDecision
from src.sensor_fusion import FusedFeatures


def build_reasons(
    features: SafetyFeatures | FusedFeatures, decision: FlagDecision, config: Config
) -> list[str]:
    if not features.incident_detected:
        return []
    reasons: list[str] = []
    stopped = features.stationary_time_s >= config.stopped_time_s
    if stopped:
        reasons.append(
            f"Car #{features.car_id} stationary for {features.stationary_time_s:.1f} s"
        )
    if stopped and features.on_racing_line:
        reasons.append(
            f"Car #{features.car_id} is within "
            f"{config.racing_line_tolerance_m:g} m of the racing-line proxy"
        )
    if features.closest_approaching_car_id is not None:
        reasons.append(
            f"Car #{features.closest_approaching_car_id} approaching at "
            f"{features.closest_approaching_car_speed_kmh:.0f} km/h, "
            f"{features.closest_car_distance_m:.0f} m behind"
        )
    if features.peak_decel_g <= config.severe_decel_g:
        reasons.append(f"Peak deceleration was {features.peak_decel_g:.1f} g")
    if features.multiple_cars_affected:
        reasons.append("Multiple cars are stopped or anomalous in the same region")
    if isinstance(features, FusedFeatures):
        if features.track_wet is True:
            reasons.append("Wet track context is available")
        if features.visibility_condition == "POOR":
            reasons.append("Poor visibility is documented")
        if features.recovery_vehicle_present is True:
            reasons.append("Recovery vehicle presence is reported in this replay")
        if features.vision_debris_visible is True:
            reasons.append("Debris is visible in the attached still image")
        if features.vision_track_blockage_fraction is not None:
            reasons.append(f"Image shows about {features.vision_track_blockage_fraction:.0%} apparent blockage")
    return reasons
