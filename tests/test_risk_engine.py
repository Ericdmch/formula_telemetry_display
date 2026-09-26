from config import Config
from src.explain import build_reasons
from src.features import SafetyFeatures
from src.model import ModelResult
from src.risk_engine import recommend_flag


def features(**overrides) -> SafetyFeatures:
    values = {
        "car_id": 12,
        "timestamp_s": 18.4,
        "sector": 4,
        "x_m": 0.0,
        "y_m": 100.0,
        "speed_kmh": 190.0,
        "stationary_time_s": 0.0,
        "peak_decel_g": -0.5,
        "on_racing_line": True,
        "closing_speed_kmh": 0.0,
        "closest_car_distance_m": 500.0,
        "nearby_cars": 0,
        "multiple_cars_affected": False,
        "closest_approaching_car_id": None,
        "closest_approaching_car_speed_kmh": 0.0,
        "incident_detected": False,
        "severe_decel": False,
    }
    values.update(overrides)
    return SafetyFeatures(**values)


def model(score: float) -> ModelResult:
    return ModelResult(
        predicted_class="HIGH_RISK" if score >= 0.75 else "MODERATE_RISK",
        probabilities={"NORMAL": 0.0, "MODERATE_RISK": 1 - score, "HIGH_RISK": score},
        risk_score=score,
        model_source="random_forest",
    )


def test_no_detected_incident_remains_green() -> None:
    decision = recommend_flag(features(), model(0.8), Config())
    assert decision.flag == "GREEN"


def test_confirmed_stop_on_line_forces_at_least_yellow() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.1,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.1), Config())

    assert decision.flag == "YELLOW"
    assert decision.rule_id == "STOPPED_ON_LINE"


def test_close_fast_traffic_forces_red_recommendation() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=5.4,
        peak_decel_g=-4.1,
        closing_speed_kmh=192,
        closest_car_distance_m=125,
        closest_approaching_car_id=7,
        closest_approaching_car_speed_kmh=192,
        incident_detected=True,
        severe_decel=True,
    )
    decision = recommend_flag(case, model(0.4), Config())

    assert decision.flag == "RED_RECOMMENDED"
    assert decision.rule_id == "ON_LINE_CLOSE_FAST_TRAFFIC"
    assert build_reasons(case, decision, Config()) == [
        "Car #12 stationary for 5.4 s",
        "Car #12 is within 3 m of the racing-line proxy",
        "Car #7 approaching at 192 km/h, 125 m behind",
        "Peak deceleration was -4.1 g",
    ]


def test_unconfirmed_deceleration_is_evidence_without_a_flag_recommendation() -> None:
    case = features(
        peak_decel_g=-3.5,
        severe_decel=True,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.9), Config())

    assert decision.flag == "GREEN"
    assert build_reasons(case, decision, Config()) == [
        "Peak deceleration was -3.5 g"
    ]


def test_multiple_affected_cars_and_high_risk_recommend_red() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.5,
        multiple_cars_affected=True,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.65), Config())

    assert decision.flag == "RED_RECOMMENDED"
    assert decision.rule_id == "MULTI_CAR_HIGH_RISK"
