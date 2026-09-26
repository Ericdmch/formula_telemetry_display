import json
from pathlib import Path

import pandas as pd

from config import Config
from src.model import ModelResult, RiskEstimator
from src.pipeline import SafetyPipeline
from src.track import load_track


class _StubEstimator:
    """Fixed low model score so the geometric rules drive the flag arc."""

    def __init__(self, score: float = 0.2):
        self._score = score

    def predict(self, features) -> ModelResult:
        return ModelResult("NORMAL", {"NORMAL": 1.0}, self._score, "stub")


def make_track(tmp_path: Path):
    track_file = tmp_path / "track.json"
    track_file.write_text(
        json.dumps({"points": [[0, 0], [1200, 0], [1200, 400], [0, 400], [0, 0]]})
    )
    return load_track(track_file)


def frame(timestamp_s: float, car7_y: float = 400, car12_speed: float = 0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_s": timestamp_s,
                "car_id": 12,
                "x_m": 0,
                "y_m": 100,
                "speed_kmh": car12_speed,
                "longitudinal_accel_g": 0,
                "sector": 4,
            },
            {
                "timestamp_s": timestamp_s,
                "car_id": 7,
                "x_m": 0,
                "y_m": car7_y,
                "speed_kmh": 192,
                "longitudinal_accel_g": 0,
                "sector": 4,
            },
        ]
    )


def test_pipeline_output_progresses_and_is_json_serializable(tmp_path: Path) -> None:
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), _StubEstimator())
    green = pipeline.update(frame(0.0))
    assert green.flag == "GREEN"
    assert green.rule_id == "NO_INCIDENT"
    assert green.incident is None

    # Car 12 stopped on the racing line, car 7 holding station.
    for tick in range(1, 21):
        double_yellow = pipeline.update(frame(tick / 10))
    assert double_yellow.flag == "DOUBLE_YELLOW"
    assert double_yellow.rule_id == "STOPPED_ON_LINE"
    assert double_yellow.incident["car_id"] == 12

    # Car 7 approaches at speed: VSC while closing, then safety car once the
    # stopped car has been stationary long enough with fast traffic on top.
    for tick in range(21, 31):
        y = 400 - (tick - 20) * 12
        vsc = pipeline.update(frame(tick / 10, y))
    assert vsc.flag == "VSC"
    assert vsc.rule_id == "STOPPED_WITH_TRAFFIC"
    assert vsc.closest_approaching_car["car_id"] == 7

    for tick in range(31, 42):
        y = 400 - (tick - 20) * 12
        safety_car = pipeline.update(frame(tick / 10, y))
    assert safety_car.flag == "SAFETY_CAR"
    assert safety_car.rule_id == "ON_LINE_CLOSE_FAST_TRAFFIC"
    assert safety_car.closest_approaching_car["distance_m"] <= 150

    payload = {
        "flag": safety_car.flag,
        "rule_id": safety_car.rule_id,
        "risk_score": safety_car.risk_score,
        "incident": safety_car.incident,
        "reasons": safety_car.reasons,
    }
    assert json.loads(json.dumps(payload))["flag"] == "SAFETY_CAR"


def test_escalated_flag_is_held_instead_of_downgraded(tmp_path: Path) -> None:
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), _StubEstimator())
    pipeline.update(frame(0.0))
    for tick in range(1, 21):
        pipeline.update(frame(tick / 10))
    for tick in range(21, 42):
        y = 400 - (tick - 20) * 12
        escalated = pipeline.update(frame(tick / 10, y))
    assert escalated.flag == "SAFETY_CAR"

    # The stopped car drives away and the field spreads: the fresh read is
    # GREEN, but the prototype latch holds the safety car recommendation.
    for tick in range(42, 62):
        held = pipeline.update(frame(tick / 10, car7_y=700, car12_speed=120))
    assert held.flag == "SAFETY_CAR"
    assert held.rule_id == "ON_LINE_CLOSE_FAST_TRAFFIC"
    assert any("held" in reason.lower() for reason in held.reasons)


def test_pipeline_reset_clears_the_flag_latch(tmp_path: Path) -> None:
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), _StubEstimator())
    pipeline.update(frame(0.0))
    for tick in range(1, 21):
        pipeline.update(frame(tick / 10))
    for tick in range(21, 42):
        y = 400 - (tick - 20) * 12
        pipeline.update(frame(tick / 10, y))
    pipeline.reset()
    fresh = pipeline.update(frame(0.0))
    assert fresh.flag == "GREEN"
    assert fresh.rule_id == "NO_INCIDENT"


def test_pipeline_rejects_out_of_order_frames(tmp_path: Path) -> None:
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), RiskEstimator())
    pipeline.update(frame(0.0))
    try:
        pipeline.update(frame(0.0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for non-increasing timestamps")
