from collections import deque
from dataclasses import dataclass

import pandas as pd

from config import Config
from src.track import Track, distance_along_track_m, forward_gap_m, project_to_track


@dataclass(frozen=True)
class Sample:
    timestamp_s: float
    speed_kmh: float
    accel_g: float
    track_s_m: float


@dataclass
class DetectedCar:
    car_id: int
    timestamp_s: float
    sector: int
    x_m: float
    y_m: float
    speed_kmh: float
    track_s_m: float
    line_offset_m: float
    stationary_time_s: float
    peak_decel_g: float
    stopped: bool
    severe_decel: bool
    on_racing_line: bool
    closing_speed_kmh: float = 0.0
    closest_car_distance_m: float = 500.0
    closest_approaching_car_id: int | None = None
    closest_approaching_car_speed_kmh: float = 0.0
    nearby_cars: int = 0
    multiple_cars_affected: bool = False

    @property
    def incident_detected(self) -> bool:
        return self.stopped or self.severe_decel or self.multiple_cars_affected


class IncidentDetector:
    def __init__(self, config: Config):
        self.config = config
        self.histories: dict[int, deque[Sample]] = {}

    def update(self, frame: pd.DataFrame, track: Track) -> list[DetectedCar]:
        if frame.empty:
            return []
        timestamp = float(frame["timestamp_s"].iloc[0])
        if frame["timestamp_s"].nunique() != 1:
            raise ValueError("detector update requires one timestamp")
        if frame["car_id"].duplicated().any():
            raise ValueError("detector update contains duplicate car")

        detected: list[DetectedCar] = []
        for row in frame.itertuples(index=False):
            car_id = int(row.car_id)
            projected = project_to_track(float(row.x_m), float(row.y_m), track)
            history = self.histories.setdefault(car_id, deque())
            history.append(
                Sample(
                    timestamp,
                    float(row.speed_kmh),
                    float(row.longitudinal_accel_g),
                    projected.s_m,
                )
            )
            while history and timestamp - history[0].timestamp_s > self.config.history_window_s:
                history.popleft()
            stationary_time = self._stationary_time(history)
            peak_decel = min(
                sample.accel_g
                for sample in history
                if timestamp - sample.timestamp_s <= self.config.decel_lookback_s + 1e-9
            )
            stopped = stationary_time + 1e-9 >= self.config.stopped_time_s
            severe = peak_decel <= self.config.severe_decel_g
            detected.append(
                DetectedCar(
                    car_id=car_id,
                    timestamp_s=timestamp,
                    sector=int(row.sector),
                    x_m=float(row.x_m),
                    y_m=float(row.y_m),
                    speed_kmh=float(row.speed_kmh),
                    track_s_m=projected.s_m,
                    line_offset_m=projected.offset_m,
                    stationary_time_s=stationary_time,
                    peak_decel_g=peak_decel,
                    stopped=stopped,
                    severe_decel=severe,
                    on_racing_line=projected.offset_m
                    <= self.config.racing_line_tolerance_m,
                )
            )

        for car in detected:
            others = [other for other in detected if other.car_id != car.car_id]
            car.nearby_cars = sum(
                distance_along_track_m(car.track_s_m, other.track_s_m, track.length_m)
                <= self.config.nearby_distance_m
                for other in others
            )
            own_affected = car.stationary_time_s >= 1.0 or car.severe_decel
            car.multiple_cars_affected = own_affected and any(
                (other.stationary_time_s >= 1.0 or other.severe_decel)
                and distance_along_track_m(
                    car.track_s_m, other.track_s_m, track.length_m
                )
                <= self.config.multicar_radius_m
                for other in others
            )
            for other in others:
                gap = forward_gap_m(car.track_s_m, other.track_s_m, track.length_m)
                closing = max(0.0, other.speed_kmh - car.speed_kmh)
                if not (
                    0 < gap <= self.config.approach_search_m
                    and other.speed_kmh >= self.config.approach_min_speed_kmh
                    and closing > 0
                    and self._gap_is_decreasing(car, other, gap, track.length_m)
                ):
                    continue
                if gap < car.closest_car_distance_m:
                    car.closest_car_distance_m = gap
                    car.closing_speed_kmh = closing
                    car.closest_approaching_car_id = other.car_id
                    car.closest_approaching_car_speed_kmh = other.speed_kmh
        return detected

    def _stationary_time(self, history: deque[Sample]) -> float:
        latest = history[-1]
        if latest.speed_kmh >= self.config.stopped_speed_kmh:
            return 0.0
        first_time = latest.timestamp_s
        later = latest
        for sample in list(history)[-2::-1]:
            if sample.speed_kmh >= self.config.stopped_speed_kmh:
                break
            if later.timestamp_s - sample.timestamp_s > self.config.max_interpolation_gap_s + 1e-9:
                break
            first_time = sample.timestamp_s
            later = sample
        return latest.timestamp_s - first_time

    def _gap_is_decreasing(
        self, car: DetectedCar, other: DetectedCar, gap: float, length_m: float
    ) -> bool:
        own_history = self.histories[car.car_id]
        other_history = self.histories[other.car_id]
        if len(own_history) < 2 or len(other_history) < 2:
            return False
        own_previous = own_history[-2]
        other_previous = other_history[-2]
        if (
            car.timestamp_s - own_previous.timestamp_s
            > self.config.max_interpolation_gap_s + 1e-9
            or other.timestamp_s - other_previous.timestamp_s
            > self.config.max_interpolation_gap_s + 1e-9
            or abs(own_previous.timestamp_s - other_previous.timestamp_s) > 1e-9
        ):
            return False
        previous_gap = forward_gap_m(
            own_previous.track_s_m, other_previous.track_s_m, length_m
        )
        return gap + 1e-6 < previous_gap <= self.config.approach_search_m + 100
