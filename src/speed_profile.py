"""Normal speed profiles: expected speed as a function of track position.

A prototype/demo reference used so that "slow" is judged relative to what is
normal *at that point on track* — a car circulating a slow corner at 60 km/h
is fine, the same speed on a 300 km/h straight is an anomaly. Built from a
scenario's own telemetry (per-bin maximum speed, so incident cars going slowly
do not drag the reference down), smoothed and gap-filled.
"""

from dataclasses import dataclass
import math

import pandas as pd

from src.track import Track, project_to_track


@dataclass(frozen=True)
class SpeedProfile:
    """Expected speed (km/h) per track bin; bin i covers [i*bin_m, (i+1)*bin_m)."""

    length_m: float
    bin_m: float
    expected_kmh: tuple[float, ...]

    def expected_speed_kmh(self, s_m: float) -> float | None:
        if not self.expected_kmh or self.length_m <= 0:
            return None
        pos = (s_m % self.length_m) / self.bin_m
        count = len(self.expected_kmh)
        i0 = int(pos) % count
        i1 = (i0 + 1) % count
        frac = pos - int(pos)
        return (1.0 - frac) * self.expected_kmh[i0] + frac * self.expected_kmh[i1]


def build_speed_profile(
    frames: list[pd.DataFrame], track: Track, bin_m: float = 25.0
) -> SpeedProfile | None:
    """Build a normal speed profile from scenario telemetry.

    Returns None when the frames carry no usable speed samples, in which case
    callers fall back to absolute speed thresholds.
    """
    if bin_m <= 0:
        raise ValueError("bin_m must be positive")
    n_bins = max(1, math.ceil(track.length_m / bin_m))
    maxima = [0.0] * n_bins
    counts = [0] * n_bins
    for frame in frames:
        for row in frame.itertuples(index=False):
            speed = float(row.speed_kmh)
            if not math.isfinite(speed) or speed < 0:
                continue
            projected = project_to_track(float(row.x_m), float(row.y_m), track)
            b = min(int(projected.s_m / bin_m), n_bins - 1)
            if speed > maxima[b]:
                maxima[b] = speed
            counts[b] += 1
    if not any(counts):
        return None
    filled = _fill_gaps(maxima, counts)
    smoothed = _smooth_circular(filled, half_window=2)
    return SpeedProfile(
        length_m=track.length_m, bin_m=bin_m, expected_kmh=tuple(smoothed)
    )


def _fill_gaps(values: list[float], counts: list[int]) -> list[float]:
    """Replace empty bins with the nearest non-empty bin value (wrapping)."""
    n = len(values)
    filled = list(values)
    for i in range(n):
        if counts[i]:
            continue
        for step in range(1, n + 1):
            ahead, behind = values[(i + step) % n], values[(i - step) % n]
            if counts[(i + step) % n]:
                filled[i] = ahead
                break
            if counts[(i - step) % n]:
                filled[i] = behind
                break
    return filled


def _smooth_circular(values: list[float], half_window: int) -> list[float]:
    """Centered moving average with wraparound for the closed loop."""
    n = len(values)
    return [
        sum(values[(i + k) % n] for k in range(-half_window, half_window + 1))
        / (2 * half_window + 1)
        for i in range(n)
    ]
