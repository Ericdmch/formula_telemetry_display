import pandas as pd
import pytest

from config import Config
from src.incident_detection import IncidentDetector
from src.pipeline import SafetyPipeline
from src.speed_profile import SpeedProfile, build_speed_profile
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


def profile_with_slow_corner() -> SpeedProfile:
    # Fixture track is 3200 m; bins 20-27 (s = 500-700 m) are a 70 km/h corner,
    # everything else a 300 km/h straight.
    bins = [300.0] * 128
    for i in range(20, 28):
        bins[i] = 70.0
    return SpeedProfile(length_m=3200.0, bin_m=25.0, expected_kmh=tuple(bins))


def drive(detector: IncidentDetector, track: Track, speed: float, x: float,
          seconds: float) -> None:
    ticks = int(seconds * 10)
    for tick in range(ticks + 1):
        detector.update(frame(tick / 10, [(7, x, 0, speed, 0)]), track)


def test_build_speed_profile_takes_binned_maxima(track: Track) -> None:
    frames = [
        frame(0.0, [(1, 100, 0, 60, 0), (2, 100, 0, 66, 0)]),
        frame(0.1, [(1, 900, 0, 290, 0), (2, 900, 0, 150, 0)]),
    ]
    profile = build_speed_profile(frames, track, bin_m=25.0)
    assert profile is not None
    # s=100 -> bin 4, max(60, 66) smoothed; s=900 -> bin 36, max(290, 150).
    assert profile.expected_speed_kmh(100) == pytest.approx(66, abs=8)
    assert profile.expected_speed_kmh(900) == pytest.approx(290, abs=12)


def test_build_speed_profile_returns_none_without_samples(track: Track) -> None:
    assert build_speed_profile([], track) is None


def test_normal_corner_pace_is_not_stationary(track: Track) -> None:
    detector = IncidentDetector(Config(), profile_with_slow_corner())
    drive(detector, track, speed=60, x=600, seconds=3.0)
    car = detector.update(frame(3.1, [(7, 600, 0, 60, 0)]), track)[0]
    assert car.stopped is False
    assert car.stationary_time_s == pytest.approx(0.0)


def test_far_below_normal_pace_counts_as_stationary(track: Track) -> None:
    detector = IncidentDetector(Config(), profile_with_slow_corner())
    # 60 km/h on a 300 km/h straight: anomalously slow, though far above the
    # old absolute 5 km/h floor.
    drive(detector, track, speed=60, x=1000, seconds=3.0)
    car = detector.update(frame(3.1, [(7, 1000, 0, 60, 0)]), track)[0]
    assert car.stopped is True


def test_parked_car_in_slow_corner_still_flagged(track: Track) -> None:
    detector = IncidentDetector(Config(), profile_with_slow_corner())
    drive(detector, track, speed=0, x=600, seconds=3.0)
    car = detector.update(frame(3.1, [(7, 600, 0, 0, 0)]), track)[0]
    assert car.stopped is True


def test_recovery_needs_near_normal_pace(track: Track) -> None:
    detector = IncidentDetector(Config(), profile_with_slow_corner())
    t = 0.0
    for _ in range(31):  # 3.0 s parked on the straight
        detector.update(frame(t, [(7, 1000, 0, 0, 0)]), track)
        t += 0.1
    car = detector.update(frame(t, [(7, 1000, 0, 0, 0)]), track)[0]
    t += 0.1
    assert car.stopped is True
    # Limping at 100 on a 300 straight: moving, but not recovered.
    for _ in range(10):
        detector.update(frame(t, [(7, 1000, 0, 100, 0)]), track)
        t += 0.1
    car = detector.update(frame(t, [(7, 1000, 0, 100, 0)]), track)[0]
    t += 0.1
    assert car.stopped is True
    # Back near normal pace: episode ends.
    car = detector.update(frame(t, [(7, 1000, 0, 250, 0)]), track)[0]
    assert car.stopped is False
    assert car.stationary_time_s == pytest.approx(0.0)


def test_pipeline_reset_keeps_speed_profile(track: Track) -> None:
    profile = profile_with_slow_corner()
    pipeline = SafetyPipeline(Config(), track=track, speed_profile=profile)
    pipeline.reset()
    assert pipeline.detector.speed_profile is profile
