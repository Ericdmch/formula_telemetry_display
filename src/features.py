from dataclasses import dataclass

from src.incident_detection import DetectedCar


FEATURE_COLUMNS = (
    "stationary_time_s",
    "peak_decel_g",
    "on_racing_line",
    "closing_speed_kmh",
    "closest_car_distance_m",
    "nearby_cars",
    "multiple_cars_affected",
)


@dataclass(frozen=True)
class SafetyFeatures:
    car_id: int
    timestamp_s: float
    sector: int
    x_m: float
    y_m: float
    speed_kmh: float
    stationary_time_s: float
    peak_decel_g: float
    on_racing_line: bool
    closing_speed_kmh: float
    closest_car_distance_m: float
    nearby_cars: int
    multiple_cars_affected: bool
    closest_approaching_car_id: int | None
    closest_approaching_car_speed_kmh: float
    incident_detected: bool
    severe_decel: bool

    def model_vector(self) -> dict[str, float | int]:
        return {
            "stationary_time_s": self.stationary_time_s,
            "peak_decel_g": self.peak_decel_g,
            "on_racing_line": int(self.on_racing_line),
            "closing_speed_kmh": self.closing_speed_kmh,
            "closest_car_distance_m": self.closest_car_distance_m,
            "nearby_cars": self.nearby_cars,
            "multiple_cars_affected": int(self.multiple_cars_affected),
        }


def extract_features(car: DetectedCar) -> SafetyFeatures:
    return SafetyFeatures(
        car_id=car.car_id,
        timestamp_s=car.timestamp_s,
        sector=car.sector,
        x_m=car.x_m,
        y_m=car.y_m,
        speed_kmh=car.speed_kmh,
        stationary_time_s=car.stationary_time_s,
        peak_decel_g=car.peak_decel_g,
        on_racing_line=car.on_racing_line,
        closing_speed_kmh=car.closing_speed_kmh,
        closest_car_distance_m=car.closest_car_distance_m,
        nearby_cars=car.nearby_cars,
        multiple_cars_affected=car.multiple_cars_affected,
        closest_approaching_car_id=car.closest_approaching_car_id,
        closest_approaching_car_speed_kmh=car.closest_approaching_car_speed_kmh,
        incident_detected=car.incident_detected,
        severe_decel=car.severe_decel,
    )
