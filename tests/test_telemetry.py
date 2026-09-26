from pathlib import Path

import pandas as pd
import pytest

from src.telemetry import load_telemetry


def write_csv(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def sample(timestamp_s: float, car_id: int, speed_kmh: float | None = 100.0) -> dict:
    return {
        "timestamp_s": timestamp_s,
        "car_id": car_id,
        "x_m": timestamp_s * 10,
        "y_m": 0.0,
        "speed_kmh": speed_kmh,
        "longitudinal_accel_g": -0.1,
        "sector": 1,
    }


def test_groups_multiple_cars_by_timestamp(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "race.csv",
        [sample(0.0, 7), sample(0.0, 12), sample(0.1, 7), sample(0.1, 12)],
    )

    frames = load_telemetry(path)

    assert len(frames) == 2
    assert frames[0]["car_id"].tolist() == [7, 12]
    assert frames[1]["timestamp_s"].tolist() == [0.1, 0.1]


def test_rejects_duplicate_car_at_timestamp(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "race.csv", [sample(0.0, 7), sample(0.0, 7)])

    with pytest.raises(ValueError, match="duplicate"):
        load_telemetry(path)


def test_rejects_out_of_order_source_rows(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "race.csv", [sample(0.1, 7), sample(0.0, 7)])

    with pytest.raises(ValueError, match="order"):
        load_telemetry(path)


def test_interpolates_one_missing_speed_between_close_samples(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "race.csv",
        [sample(0.0, 7, 100.0), sample(0.1, 7, None), sample(0.2, 7, 80.0)],
    )

    frames = load_telemetry(path)

    assert frames[1].iloc[0]["speed_kmh"] == pytest.approx(90.0)
    assert bool(frames[1].iloc[0]["speed_imputed"]) is True


def test_does_not_turn_long_missing_gap_into_zero_speed(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "race.csv",
        [sample(0.0, 7, 100.0), sample(0.4, 7, None), sample(0.8, 7, 80.0)],
    )

    frames = load_telemetry(path)

    assert [len(frame) for frame in frames] == [1, 1]
    assert frames[1].iloc[0]["speed_kmh"] == 80.0

