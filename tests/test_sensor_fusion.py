from config import Config
from src.features import FEATURE_COLUMNS, SafetyFeatures
from src.model import ModelResult
from src.risk_engine import recommend_flag
from src.sensor_fusion import EnvironmentalContext, VisualFeatures, fuse_features
from src.vision import VisionAnalyzer


def stopped_car() -> SafetyFeatures:
    return SafetyFeatures(
        car_id=99, timestamp_s=5, sector=3, x_m=200, y_m=400,
        speed_kmh=0, stationary_time_s=3, peak_decel_g=-3,
        on_racing_line=False, closing_speed_kmh=0, closest_car_distance_m=500,
        nearby_cars=0, multiple_cars_affected=False,
        closest_approaching_car_id=None, closest_approaching_car_speed_kmh=0,
        incident_detected=True, severe_decel=True,
    )


def low_model() -> ModelResult:
    return ModelResult("NORMAL", {"NORMAL": 1, "MODERATE_RISK": 0, "HIGH_RISK": 0}, 0, "rules_fallback")


def test_fusion_preserves_v1_model_vector_and_uses_available_context() -> None:
    base = stopped_car()
    environment = EnvironmentalContext(
        sector=3, track_wet=True, visibility_condition="POOR",
        recovery_vehicle_present=True, source="FIA", quality="RECONSTRUCTED_TIMING",
    )
    fused = fuse_features(base, environment)
    assert list(fused.model_vector()) == list(FEATURE_COLUMNS)
    assert fused.model_vector() == base.model_vector()
    decision = recommend_flag(fused, low_model(), Config())
    assert decision.rule_id == "RECOVERY_WET_POOR_VISIBILITY"
    assert decision.flag == "RED_RECOMMENDED"
    assert recommend_flag(fuse_features(base), low_model(), Config()).flag == "GREEN"


def test_visual_facts_require_confidence_and_never_supply_a_flag() -> None:
    base = stopped_car()
    low = VisualFeatures(vehicle_on_track=True, track_blockage_fraction=0.8, confidence=0.4)
    high = VisualFeatures(vehicle_on_track=True, track_blockage_fraction=0.8, confidence=0.9)
    assert recommend_flag(fuse_features(base, visual=low), low_model(), Config()).flag == "GREEN"
    decision = recommend_flag(fuse_features(base, visual=high), low_model(), Config())
    assert decision.rule_id == "VISUAL_BLOCKAGE_WITH_STOP"
    assert not hasattr(high, "flag")


def test_optional_image_analyzer_omits_unavailable_vision() -> None:
    assert VisionAnalyzer().analyze(b"one still image") is None
    visual = VisualFeatures(debris_visible=True, confidence=0.8, source="manual")
    assert VisionAnalyzer(lambda image: visual).analyze(b"one still image") == visual
