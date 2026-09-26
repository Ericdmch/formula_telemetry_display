from pathlib import Path

import joblib
import numpy as np
import pytest

from src.features import FEATURE_COLUMNS, SafetyFeatures
from src.model import RiskEstimator, generate_training_data, train_model


def features(
    stationary_time_s: float = 0.0,
    peak_decel_g: float = -0.5,
    on_racing_line: bool = False,
    closing_speed_kmh: float = 0.0,
    closest_car_distance_m: float = 500.0,
    nearby_cars: int = 0,
    multiple_cars_affected: bool = False,
) -> SafetyFeatures:
    return SafetyFeatures(
        car_id=12,
        timestamp_s=18.4,
        sector=4,
        x_m=0,
        y_m=100,
        speed_kmh=0,
        stationary_time_s=stationary_time_s,
        peak_decel_g=peak_decel_g,
        on_racing_line=on_racing_line,
        closing_speed_kmh=closing_speed_kmh,
        closest_car_distance_m=closest_car_distance_m,
        nearby_cars=nearby_cars,
        multiple_cars_affected=multiple_cars_affected,
        closest_approaching_car_id=7 if closing_speed_kmh else None,
        closest_approaching_car_speed_kmh=closing_speed_kmh,
        incident_detected=stationary_time_s >= 2 or peak_decel_g <= -2.5,
        severe_decel=peak_decel_g <= -2.5,
    )


def test_synthetic_training_rows_are_reproducible_and_balanced() -> None:
    first = generate_training_data(seed=42, per_class=20)
    second = generate_training_data(seed=42, per_class=20)

    assert first.equals(second)
    assert first["label"].value_counts().sort_index().tolist() == [20, 20, 20]
    assert all(column in first for column in FEATURE_COLUMNS)
    assert "car_id" not in first


def test_model_artifact_predicts_severity_from_seven_features(tmp_path: Path) -> None:
    table = generate_training_data(seed=42, per_class=80)
    path = tmp_path / "risk_model.joblib"

    report = train_model(table, path)
    estimator = RiskEstimator.load_or_fallback(path)
    normal = estimator.predict(features())
    high = estimator.predict(
        features(
            stationary_time_s=6,
            peak_decel_g=-4.1,
            on_racing_line=True,
            closing_speed_kmh=190,
            closest_car_distance_m=90,
            nearby_cars=2,
        )
    )

    assert path.exists()
    assert report.confusion_matrix.shape == (3, 3)
    assert estimator.model_source == "random_forest"
    assert sum(high.probabilities.values()) == pytest.approx(1)
    assert high.risk_score == pytest.approx(
        0.5 * high.probabilities["MODERATE_RISK"]
        + high.probabilities["HIGH_RISK"]
    )
    assert high.risk_score > normal.risk_score


def test_missing_or_incompatible_artifact_uses_visible_rule_fallback(tmp_path: Path) -> None:
    absent = RiskEstimator.load_or_fallback(tmp_path / "absent.joblib")
    high = absent.predict(
        features(
            stationary_time_s=5,
            peak_decel_g=-4,
            on_racing_line=True,
            closing_speed_kmh=192,
            closest_car_distance_m=125,
        )
    )
    assert high.model_source == "rules_fallback"
    assert high.risk_score == pytest.approx(0.9)
    assert high.probabilities["HIGH_RISK"] == pytest.approx(0.8)

    invalid_path = tmp_path / "invalid.joblib"
    joblib.dump({"schema_version": 999}, invalid_path)
    invalid = RiskEstimator.load_or_fallback(invalid_path)
    assert invalid.model_source == "rules_fallback"


def test_model_with_wrong_fitted_feature_names_uses_fallback(tmp_path: Path) -> None:
    path = tmp_path / "wrong_features.joblib"
    train_model(generate_training_data(per_class=20), path)
    bundle = joblib.load(path)
    bundle["estimator"].feature_names_in_ = np.array(
        ["wrong_name", *FEATURE_COLUMNS[1:]]
    )
    joblib.dump(bundle, path)

    estimator = RiskEstimator.load_or_fallback(path)

    assert estimator.model_source == "rules_fallback"
    assert (
        estimator.predict(features(stationary_time_s=5)).model_source
        == "rules_fallback"
    )


def test_inference_failure_switches_loaded_model_to_fallback(tmp_path: Path) -> None:
    path = tmp_path / "risk_model.joblib"
    train_model(generate_training_data(per_class=20), path)
    estimator = RiskEstimator.load_or_fallback(path)
    estimator.estimator.feature_names_in_ = np.array(
        ["wrong_name", *FEATURE_COLUMNS[1:]]
    )

    result = estimator.predict(features(stationary_time_s=5))

    assert result.model_source == "rules_fallback"
    assert result.risk_score == pytest.approx(0.25)
