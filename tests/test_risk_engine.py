from dataclasses import asdict

from config import Config
from src.explain import build_reasons
from src.features import SafetyFeatures
from src.model import ModelResult
from src.risk_engine import latch_flag, recommend_flag
from src.sensor_fusion import FusedFeatures


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


def fused_features(**overrides) -> FusedFeatures:
    values = asdict(features())
    values.update(overrides)
    return FusedFeatures(**values)


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


def test_confirmed_stop_on_line_recommends_double_yellow() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.1,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.1), Config())

    assert decision.flag == "DOUBLE_YELLOW"
    assert decision.rule_id == "STOPPED_ON_LINE"


def test_confirmed_stop_off_line_gets_yellow_then_vsc_when_prolonged() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.1,
        on_racing_line=False,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.1), Config())

    assert decision.flag == "YELLOW"
    assert decision.rule_id == "STOPPED_CAR_YELLOW"

    prolonged = features(
        speed_kmh=0,
        stationary_time_s=5.1,
        on_racing_line=False,
        incident_detected=True,
    )
    decision = recommend_flag(prolonged, model(0.1), Config())
    assert decision.flag == "VSC"
    assert decision.rule_id == "SUSTAINED_STOP_VSC"


def test_stopped_with_approaching_traffic_recommends_vsc() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.5,
        on_racing_line=False,
        closing_speed_kmh=120,
        closest_car_distance_m=180,
        closest_approaching_car_id=7,
        closest_approaching_car_speed_kmh=120,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.2), Config())

    assert decision.flag == "VSC"
    assert decision.rule_id == "STOPPED_WITH_TRAFFIC"


def test_close_fast_traffic_escalates_to_safety_car() -> None:
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

    assert decision.flag == "SAFETY_CAR"
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


def test_multiple_affected_cars_and_high_risk_recommend_safety_car() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.5,
        multiple_cars_affected=True,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.65), Config())

    assert decision.flag == "SAFETY_CAR"
    assert decision.rule_id == "MULTI_CAR_HIGH_RISK"


def test_high_model_risk_alone_recommends_yellow_review() -> None:
    case = features(
        speed_kmh=0,
        stationary_time_s=2.5,
        on_racing_line=False,
        incident_detected=True,
    )
    decision = recommend_flag(case, model(0.9), Config())

    assert decision.flag == "YELLOW"
    assert decision.rule_id == "MODEL_RISK_HIGH_REVIEW"


def test_latch_flag_holds_vsc_and_above() -> None:
    assert latch_flag("GREEN", "VSC") == "VSC"
    assert latch_flag("VSC", "GREEN") == "VSC"
    assert latch_flag("VSC", "DOUBLE_YELLOW") == "VSC"
    assert latch_flag("SAFETY_CAR", "YELLOW") == "SAFETY_CAR"
    assert latch_flag("RED_RECOMMENDED", "GREEN") == "RED_RECOMMENDED"
    assert latch_flag("SAFETY_CAR", "RED_RECOMMENDED") == "RED_RECOMMENDED"


def test_latch_flag_allows_downgrade_below_vsc() -> None:
    assert latch_flag("GREEN", "GREEN") == "GREEN"
    assert latch_flag("YELLOW", "GREEN") == "GREEN"
    assert latch_flag("DOUBLE_YELLOW", "GREEN") == "GREEN"
    assert latch_flag("DOUBLE_YELLOW", "YELLOW") == "YELLOW"


def test_debris_report_recommends_vsc_without_stopped_car() -> None:
    case = fused_features(debris_reported=True)
    decision = recommend_flag(case, model(0.2), Config())

    assert decision.flag == "VSC"
    assert decision.rule_id == "DEBRIS_REPORTED_ON_TRACK"


def test_debris_report_beats_high_model_risk_band() -> None:
    case = fused_features(debris_reported=True)
    decision = recommend_flag(case, model(0.9), Config())

    assert decision.flag == "VSC"
    assert decision.rule_id == "DEBRIS_REPORTED_ON_TRACK"


def test_debris_report_does_not_override_safety_car_evidence() -> None:
    case = fused_features(
        debris_reported=True,
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

    assert decision.flag == "SAFETY_CAR"
    assert decision.rule_id == "ON_LINE_CLOSE_FAST_TRAFFIC"


def test_no_debris_report_keeps_model_band_path() -> None:
    case = fused_features(debris_reported=None)
    decision = recommend_flag(case, model(0.9), Config())

    assert decision.flag == "GREEN"
    assert decision.rule_id == "NO_INCIDENT"
