from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "timestamp_s",
    "car_id",
    "x_m",
    "y_m",
    "speed_kmh",
    "longitudinal_accel_g",
    "sector",
)
MAX_INTERPOLATION_GAP_S = 0.3


def load_telemetry(path: Path) -> list[pd.DataFrame]:
    """Load one row per car and timestamp into ordered replay frames."""
    table = pd.read_csv(path)
    missing = set(REQUIRED_COLUMNS) - set(table.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if table.empty:
        raise ValueError("telemetry file is empty")

    for column in REQUIRED_COLUMNS:
        original = table[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & numeric.isna()
        if invalid.any():
            raise ValueError(f"invalid numeric value in {column}")
        table[column] = numeric

    identifiers = ("timestamp_s", "car_id", "x_m", "y_m", "sector")
    if table[list(identifiers)].isna().any().any():
        raise ValueError("missing timestamp, car, position, or sector")
    if not np.isfinite(table[list(identifiers)].to_numpy(dtype=float)).all():
        raise ValueError("nonfinite telemetry identifier or position")
    if (table["timestamp_s"] < 0).any():
        raise ValueError("timestamp_s must be nonnegative")
    if ((table["car_id"] <= 0) | (table["car_id"] % 1 != 0)).any():
        raise ValueError("car_id must be a positive integer")
    if (~table["sector"].isin([1, 2, 3, 4])).any():
        raise ValueError("sector must be 1 through 4")
    if table.duplicated(["timestamp_s", "car_id"]).any():
        raise ValueError("duplicate timestamp/car_id pair")
    if (table["timestamp_s"].diff().dropna() < 0).any():
        raise ValueError("source rows are out of time order")
    if (table.groupby("car_id")["timestamp_s"].diff().dropna() <= 0).any():
        raise ValueError("car timestamps are out of order")

    table["speed_imputed"] = False
    table["accel_imputed"] = False
    for car_id, group in table.groupby("car_id", sort=False):
        _repair_column(table, group, "speed_kmh", "speed_imputed")
        _repair_column(table, group, "longitudinal_accel_g", "accel_imputed")

    table = table.dropna(subset=["speed_kmh", "longitudinal_accel_g"]).copy()
    if not np.isfinite(table[["speed_kmh", "longitudinal_accel_g"]].to_numpy()).all():
        raise ValueError("nonfinite speed or acceleration")
    if ((table["speed_kmh"] < 0) | (table["speed_kmh"] > 400)).any():
        raise ValueError("speed_kmh outside 0–400")
    if ((table["longitudinal_accel_g"] < -8) | (table["longitudinal_accel_g"] > 5)).any():
        raise ValueError("longitudinal_accel_g outside -8 to +5")

    table["car_id"] = table["car_id"].astype(int)
    table["sector"] = table["sector"].astype(int)
    table = table.sort_values(["timestamp_s", "car_id"])
    return [
        frame.reset_index(drop=True)
        for _, frame in table.groupby("timestamp_s", sort=True)
    ]


def _repair_column(
    table: pd.DataFrame, group: pd.DataFrame, column: str, flag_column: str
) -> None:
    values = group[column]
    for row_index in group.index[values.isna()]:
        before = group.loc[(group.index < row_index) & group[column].notna()]
        after = group.loc[(group.index > row_index) & group[column].notna()]
        if before.empty or after.empty:
            continue
        prior = before.iloc[-1]
        following = after.iloc[0]
        time = float(table.at[row_index, "timestamp_s"])
        left_gap = time - float(prior["timestamp_s"])
        right_gap = float(following["timestamp_s"]) - time
        if left_gap > MAX_INTERPOLATION_GAP_S or right_gap > MAX_INTERPOLATION_GAP_S:
            continue
        fraction = left_gap / (left_gap + right_gap)
        table.at[row_index, column] = float(prior[column]) + fraction * (
            float(following[column]) - float(prior[column])
        )
        table.at[row_index, flag_column] = True
