import json
from pathlib import Path

import pandas as pd

from config import Config
from src.model import RiskEstimator
from src.pipeline import SafetyPipeline
from src.track import load_track


def make_track(tmp_path: Path):
    path = tmp_path / "track.json"
    path.write_text('{"points": [[0,0],[1200,0],[1200,400],[0,400],[0,0]]}')
    return load_track(path)


def frame(t: float, car7_y: float = 400) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_s": t,
                "car_id": 12,
                "x_m": 0,
                "y_m": 100,
                "speed_kmh": 0,
                "longitudinal_accel_g": 0,
                "sector": 4,
            },
            {
                "timestamp_s": t,
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
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), RiskEstimator())
    green = pipeline.update(frame(0.0)).to_dict()
    for tick in range(1, 21):
        yellow = pipeline.update(frame(tick / 10)).to_dict()
    for tick in range(21, 42):
        y = 400 - (tick - 20) * 12
        red = pipeline.update(frame(tick / 10, y)).to_dict()

    assert green["flag"] == "GREEN"
    assert green["incident"] is None
    assert len(green["vehicles"]) == 2
    assert yellow["flag"] == "YELLOW"
    assert yellow["incident"]["car_id"] == 12
    assert red["flag"] == "RED_RECOMMENDED"
    assert red["closest_approaching_car"]["car_id"] == 7
    assert red["rule_id"] == "ON_LINE_CLOSE_FAST_TRAFFIC"
    json.dumps(red)


def test_missing_frame_is_not_displayed_as_green(tmp_path: Path) -> None:
    pipeline = SafetyPipeline(Config(), make_track(tmp_path), RiskEstimator())
    pipeline.update(frame(0.0))
    unavailable = pipeline.update(frame(1.2)).to_dict()

    assert unavailable["status"] == "DATA_UNAVAILABLE"
    assert unavailable["flag"] is None
    assert unavailable["quality_notes"]
