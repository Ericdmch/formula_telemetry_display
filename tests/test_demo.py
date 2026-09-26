from pathlib import Path

import pytest

from config import Config
from scripts.generate_demo_race import generate_demo_race
from scripts.run_demo import replay
from src.model import RiskEstimator
from src.pipeline import SafetyPipeline
from src.track import load_track


def make_track(tmp_path: Path):
    path = tmp_path / "track.json"
    path.write_text('{"points": [[0,0],[1200,0],[1200,400],[0,400],[0,0]]}')
    return load_track(path)


def test_prerecorded_demo_is_offline_and_repeats_flag_progression(tmp_path: Path) -> None:
    track = make_track(tmp_path)
    path = tmp_path / "demo.csv"
    table = generate_demo_race(path, track)

    def run():
        return replay(path, SafetyPipeline(Config(), track, RiskEstimator()))

    first = run()
    second = run()
    first_flags = [result.flag for result in first]

    assert path.exists()
    assert len(table) == 804
    assert set(table["car_id"]) == {3, 7, 12, 21}
    assert not table.isna().any().any()
    assert first[0].flag == "GREEN"
    assert any(
        result.features is not None
        and result.features["peak_decel_g"] <= -2.5
        for result in first
        if 10 <= result.timestamp_s <= 13
    )
    assert any(
        result.flag == "YELLOW" and result.timestamp_s <= 15.1
        for result in first
    )
    assert any(
        result.flag == "RED_RECOMMENDED" and result.timestamp_s <= 19.1
        for result in first
    )
    assert first_flags == [result.flag for result in second]
    stopped = table[(table["car_id"] == 12) & (table["timestamp_s"] == 15.0)].iloc[0]
    assert stopped["x_m"] == pytest.approx(0, abs=5)
    assert stopped["y_m"] == pytest.approx(100, abs=10)
    assert stopped["sector"] == 4


def test_committed_model_replay_does_not_downgrade_before_red() -> None:
    config = Config()
    results = replay(config.demo_path, SafetyPipeline(config))
    flags = [result.flag for result in results]

    assert results[0].model_source == "random_forest"
    first_yellow = flags.index("YELLOW")
    first_red = flags.index("RED_RECOMMENDED")
    assert "GREEN" not in flags[first_yellow:first_red]
    assert results[first_yellow].timestamp_s <= 15.1
    assert results[first_red].timestamp_s <= 19.1
