import pandas as pd
import pytest

from config import Config
from src.incident_detection import IncidentDetector
from src.track import Track, load_track


@pytest.fixture
def track(tmp_path) -> Track:
    path = tmp_path / "track.json"
    path.write_text('{"points": [[0,0],[1200,0],[1200,400],[0,400],[0,0]]}')
    return load_track(path)


def frame(t: float, cars: list[tuple[int, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_s": t,
                "car_id": car_id,
                "x_m": x,
                "y_m": y,
                "speed_kmh": speed,
                "longitudinal_accel_g": accel,
                "sector": 4,
            }
            for car_id, x, y, speed, accel in cars
        ]
    )


def test_stopped_car_requires_two_continuous_seconds(track: Track) -> None:
    detector = IncidentDetector(Config())
    detected = None
    for tick in range(21):
        detected = detector.update(frame(tick / 10, [(12, 0, 100, 0, 0)]), track)[0]
        if tick == 19:
            assert detected.stopped is False

    assert detected is not None
    assert detected.stopped is True
    assert detected.stationary_time_s == pytest.approx(2.0)
    assert detected.on_racing_line is True


def test_severe_deceleration_uses_trailing_two_seconds(track: Track) -> None:
    detector = IncidentDetector(Config())
    car = detector.update(frame(0.0, [(12, 0, 100, 210, -3.0)]), track)[0]

    assert car.severe_decel is True
    assert car.peak_decel_g == pytest.approx(-3.0)
    assert car.stopped is False


def test_moving_car_on_centerline_is_not_an_obstruction(track: Track) -> None:
    detector = IncidentDetector(Config())
    car = detector.update(frame(0.0, [(12, 0, 100, 210, 0)]), track)[0]

    assert car.on_racing_line is True
    assert car.stopped is False
    assert car.incident_detected is False


def test_approach_requires_decreasing_forward_gap(track: Track) -> None:
    detector = IncidentDetector(Config())
    for tick in range(21):
        y = 225 + (20 - tick) * 5
        detector.update(
            frame(tick / 10, [(12, 0, 100, 0, 0), (7, 0, y, 192, 0)]),
            track,
        )
    car = detector.update(
        frame(2.1, [(12, 0, 100, 0, 0), (7, 0, 220, 192, 0)]), track
    )[0]

    assert car.closest_approaching_car_id == 7
    assert car.closest_car_distance_m == pytest.approx(120)
    assert car.closing_speed_kmh == pytest.approx(192)


def test_two_stopped_cars_near_each_other_are_multicar_incident(track: Track) -> None:
    detector = IncidentDetector(Config())
    for tick in range(21):
        cars = [(12, 0, 100, 0, 0), (13, 0, 125, 0, 0)]
        detected = detector.update(frame(tick / 10, cars), track)

    assert all(car.multiple_cars_affected for car in detected)


def test_gap_in_samples_resets_stationary_duration(track: Track) -> None:
    detector = IncidentDetector(Config())
    for tick in range(11):
        detector.update(frame(tick / 10, [(12, 0, 100, 0, 0)]), track)
    car = detector.update(frame(1.5, [(12, 0, 100, 0, 0)]), track)[0]

    assert car.stationary_time_s == 0
    assert car.stopped is False
