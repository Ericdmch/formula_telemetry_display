from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from src.features import FEATURE_COLUMNS, SafetyFeatures


CLASS_NAMES = {0: "NORMAL", 1: "MODERATE_RISK", 2: "HIGH_RISK"}
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelResult:
    predicted_class: str
    probabilities: dict[str, float]
    risk_score: float
    model_source: str


@dataclass(frozen=True)
class EvaluationReport:
    confusion_matrix: np.ndarray
    classification_report: str
    feature_importances: dict[str, float]


def generate_training_data(seed: int = 42, per_class: int = 1200) -> pd.DataFrame:
    """Generate balanced, varied *simulated* severity examples."""
    if per_class < 4:
        raise ValueError("per_class must be at least 4")
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for label in CLASS_NAMES:
        for _ in range(per_class):
            family = int(rng.integers(0, 3))
            if label == 0:
                values = (
                    float(rng.uniform(0, 0.4)),
                    -float(rng.uniform(0.1, 2.0)),
                    int(rng.random() < 0.8),
                    0.0,
                    500.0,
                    int(rng.integers(0, 3)),
                    0,
                )
                family_name = "normal_racing"
            elif label == 1 and family == 0:
                values = (
                    0.0,
                    -float(rng.uniform(2.0, 3.4)),
                    int(rng.random() < 0.8),
                    0.0,
                    500.0,
                    int(rng.integers(0, 3)),
                    0,
                )
                family_name = "slowdown"
            elif label == 1 and family == 1:
                values = (
                    float(rng.uniform(2.0, 6.0)),
                    -float(rng.uniform(1.0, 3.1)),
                    0,
                    float(rng.uniform(40, 90)),
                    float(rng.uniform(180, 250)),
                    int(rng.integers(1, 3)),
                    0,
                )
                family_name = "off_line_stop"
            elif label == 1:
                has_traffic = rng.random() < 0.5
                values = (
                    float(rng.uniform(1.5, 3.5)),
                    -float(rng.uniform(1.0, 2.5)),
                    1,
                    float(rng.uniform(50, 100)) if has_traffic else 0.0,
                    float(rng.uniform(180, 250)) if has_traffic else 500.0,
                    int(rng.integers(0, 3)),
                    0,
                )
                family_name = "brief_on_line_stop"
            elif label == 2 and family == 1:
                values = (
                    float(rng.uniform(2.0, 8.0)),
                    -float(rng.uniform(2.0, 5.0)),
                    int(rng.random() < 0.8),
                    float(rng.uniform(80, 180)),
                    float(rng.uniform(30, 180)),
                    int(rng.integers(2, 5)),
                    1,
                )
                family_name = "multi_car"
            else:
                values = (
                    float(rng.uniform(3.0, 8.0)),
                    -float(rng.uniform(2.5, 5.2)),
                    1,
                    float(rng.uniform(120, 220)),
                    float(rng.uniform(30, 170)),
                    int(rng.integers(1, 5)),
                    0,
                )
                family_name = "on_line_fast_traffic"
            rows.append(
                {
                    **dict(zip(FEATURE_COLUMNS, values)),
                    "label": label,
                    "scenario_family": family_name,
                }
            )
    return pd.DataFrame(rows)


def train_model(table: pd.DataFrame, model_path: Path) -> EvaluationReport:
    missing = set(FEATURE_COLUMNS) - set(table.columns)
    if missing or "label" not in table:
        raise ValueError(f"missing training columns: {sorted(missing | ({'label'} if 'label' not in table else set()))}")
    if set(table["label"]) != set(CLASS_NAMES):
        raise ValueError("training data must contain all three classes")
    x = table.loc[:, FEATURE_COLUMNS]
    y = table["label"]
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, stratify=y, random_state=42
    )
    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=4,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    report = EvaluationReport(
        confusion_matrix=confusion_matrix(y_test, predictions, labels=[0, 1, 2]),
        classification_report=classification_report(
            y_test,
            predictions,
            labels=[0, 1, 2],
            target_names=list(CLASS_NAMES.values()),
            zero_division=0,
        ),
        feature_importances=dict(
            zip(FEATURE_COLUMNS, map(float, model.feature_importances_))
        ),
    )
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "schema_version": SCHEMA_VERSION,
            "feature_columns": FEATURE_COLUMNS,
            "class_names": CLASS_NAMES,
            "seed": 42,
            "estimator": model,
        },
        model_path,
    )
    return report


class RiskEstimator:
    def __init__(self, estimator: RandomForestClassifier | None = None):
        self.estimator = estimator
        self.model_source = (
            "random_forest" if estimator is not None else "rules_fallback"
        )

    @classmethod
    def load_or_fallback(cls, path: Path) -> "RiskEstimator":
        try:
            bundle = joblib.load(path)
            if (
                bundle["schema_version"] != SCHEMA_VERSION
                or tuple(bundle["feature_columns"]) != FEATURE_COLUMNS
                or bundle["class_names"] != CLASS_NAMES
                or set(bundle["estimator"].classes_) != set(CLASS_NAMES)
            ):
                raise ValueError("model schema mismatch")
            return cls(bundle["estimator"])
        except Exception:
            return cls()

    def predict(self, features: SafetyFeatures) -> ModelResult:
        if self.estimator is None:
            score = self._fallback_score(features)
            if score <= 0.5:
                probabilities = {
                    "NORMAL": 1 - 2 * score,
                    "MODERATE_RISK": 2 * score,
                    "HIGH_RISK": 0.0,
                }
            else:
                probabilities = {
                    "NORMAL": 0.0,
                    "MODERATE_RISK": 2 - 2 * score,
                    "HIGH_RISK": 2 * score - 1,
                }
        else:
            vector = pd.DataFrame([features.model_vector()], columns=FEATURE_COLUMNS)
            values = self.estimator.predict_proba(vector)[0]
            probabilities = {
                CLASS_NAMES[int(class_id)]: float(probability)
                for class_id, probability in zip(self.estimator.classes_, values)
            }
        score = (
            0.5 * probabilities["MODERATE_RISK"] + probabilities["HIGH_RISK"]
        )
        predicted_class = max(probabilities, key=probabilities.get)
        return ModelResult(
            predicted_class=predicted_class,
            probabilities=probabilities,
            risk_score=float(score),
            model_source=self.model_source,
        )

    @staticmethod
    def _fallback_score(features: SafetyFeatures) -> float:
        stopped = features.stationary_time_s >= 2.0
        score = (
            0.25 * stopped
            + 0.20 * (stopped and features.on_racing_line)
            + 0.30
            * (
                features.closest_car_distance_m <= 150
                and features.closing_speed_kmh >= 120
            )
            + 0.15 * features.severe_decel
            + 0.30 * features.multiple_cars_affected
        )
        return min(1.0, score)
