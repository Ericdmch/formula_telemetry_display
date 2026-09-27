from pathlib import Path
import shutil

import pytest

from src.historical import load_scenario
from src.incident_media import describe_incident_still, load_incident_still


@pytest.mark.parametrize("scenario_id, expected_phrase", [
    ("2024_azerbaijan_perez_sainz", "red Ferrari"),
    ("2024_qatar_mirror_debris", "dark fragment"),
    ("2021_azerbaijan_verstappen", "Red Bull race car"),
    ("2022_canada_tsunoda", "AlphaTauri race car"),
])
def test_bundled_still_matches_scenario_and_enters_at_incident(
    scenario_id: str, expected_phrase: str
) -> None:
    scenario = load_scenario(scenario_id)
    still = load_incident_still(scenario.path)
    assert still is not None
    assert still.available_at_relative_s == 0
    assert expected_phrase in describe_incident_still(still)
    assert still.image_path.is_file()

    before = next(frame for frame in scenario.frames if scenario.relative_time(
        float(frame["timestamp_s"].iloc[0])) < 0)
    at_incident = next(frame for frame in scenario.frames if scenario.relative_time(
        float(frame["timestamp_s"].iloc[0])) == 0)
    assert scenario.visual_at(before) is None
    assert scenario.visual_at(at_incident) == still.features


def test_changed_image_cannot_keep_reviewed_description(tmp_path: Path) -> None:
    scenario = load_scenario("2024_qatar_mirror_debris")
    shutil.copy(scenario.path / "visual_features.json", tmp_path / "visual_features.json")
    (tmp_path / "incident.png").write_bytes(b"different image")
    with pytest.raises(ValueError, match="does not match"):
        load_incident_still(tmp_path)
