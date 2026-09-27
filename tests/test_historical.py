import json
from pathlib import Path
import shutil

import pytest

from src.historical import SCENARIO_ROOT, load_scenario, scenario_ids
from src.pipeline import SafetyPipeline
from src.sensor_fusion import VisualFeatures
from src.track import load_track


@pytest.fixture
def portable_root(tmp_path: Path) -> Path:
    for scenario_id in scenario_ids():
        source = SCENARIO_ROOT / scenario_id
        destination = tmp_path / scenario_id
        destination.mkdir()
        shutil.copy(source / "scenario.json", destination / "scenario.json")
        shutil.copy(source / "reconstruction.csv", destination / "reconstruction.csv")
    return tmp_path


def test_all_portable_scenarios_normalize_incident_and_label_motion(portable_root: Path) -> None:
    assert len(scenario_ids(portable_root)) == 4
    for scenario_id in scenario_ids(portable_root):
        scenario = load_scenario(scenario_id, portable_root)
        assert scenario.relative_time(scenario.frames[0]["timestamp_s"].iloc[0]) == -5
        assert any(scenario.relative_time(frame["timestamp_s"].iloc[0]) == 0 for frame in scenario.frames)
        assert scenario.metadata["data_quality"] == "HISTORICALLY_GROUNDED_RECONSTRUCTION"
        assert scenario.metadata["field_provenance"]["speed_kmh"] == "SIMULATED"
        assert {origin for frame in scenario.frames for origin in frame["speed_origin"]} == {"SIMULATED"}


def test_invalid_schema_and_actual_action_order_rejected(portable_root: Path) -> None:
    path = portable_root / "2024_azerbaijan_perez_sainz" / "scenario.json"
    data = json.loads(path.read_text())
    data["actual_control_actions"] = list(reversed(data["actual_control_actions"]))
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="out of time order"):
        load_scenario("2024_azerbaijan_perez_sainz", portable_root)


def test_incomplete_measured_cache_falls_back_to_labelled_reconstruction(portable_root: Path) -> None:
    folder = portable_root / "2024_azerbaijan_perez_sainz"
    shutil.copy(folder / "reconstruction.csv", folder / "telemetry.csv")
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert scenario.metadata["data_quality"] == "HISTORICALLY_GROUNDED_RECONSTRUCTION"
    assert scenario.track_path.parent != folder
    assert scenario.frames[0]["speed_origin"].iloc[0] == "SIMULATED"


def test_actual_state_is_separate_and_untimed_actions_do_not_gain_seconds(portable_root: Path) -> None:
    baku = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert baku.actual_state(9) == "GREEN / SESSION RUNNING"
    assert baku.actual_state(10) == "DOUBLE YELLOW (LOCAL MESSAGE)"
    assert baku.actual_state(12) == "YELLOW (LOCAL MESSAGE)"
    assert baku.actual_state(87) == "VSC"


def test_missing_optional_weather_and_visual_do_not_change_pipeline_contract(portable_root: Path) -> None:
    path = portable_root / "2024_azerbaijan_perez_sainz" / "scenario.json"
    data = json.loads(path.read_text())
    data.pop("weather_context")
    path.write_text(json.dumps(data))
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert scenario.visual_at(scenario.frames[0]) is None
    pipeline = SafetyPipeline(track=load_track(scenario.track_path))
    results = [scenario.update_pipeline(pipeline, frame) for frame in scenario.frames[:55]]
    assert results[0].flag == "GREEN"
    assert all(result.status == "OK" for result in results)
    assert any(result.incident is not None for result in results)
    assert all(result.context_evidence is None or result.context_evidence["vision_source"] is None for result in results)


def test_cached_visual_facts_are_not_visible_before_availability(portable_root: Path) -> None:
    folder = portable_root / "2024_azerbaijan_perez_sainz"
    (folder / "visual_features.json").write_text(json.dumps({
        "available_at_relative_s": 4.0,
        "features": {"debris_visible": True, "confidence": 0.9, "source": "cached"},
    }))
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    before = next(f for f in scenario.frames if abs(scenario.relative_time(f["timestamp_s"].iloc[0]) - 3.8) < 1e-6)
    after = next(f for f in scenario.frames if abs(scenario.relative_time(f["timestamp_s"].iloc[0]) - 4.0) < 1e-6)
    assert scenario.visual_at(before) is None
    assert scenario.visual_at(after).debris_visible is True


def test_attached_still_image_facts_enter_only_subsequent_frames(portable_root: Path) -> None:
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    pipeline = SafetyPipeline(track=load_track(scenario.track_path))
    visual = VisualFeatures(debris_visible=True, confidence=0.8, source="manual")
    before_sources = []
    after_sources = []
    for frame in scenario.frames[:75]:
        relative = scenario.relative_time(float(frame["timestamp_s"].iloc[0]))
        result = scenario.update_pipeline(pipeline, frame, visual if relative >= 4 else None)
        source = result.context_evidence and result.context_evidence["vision_source"]
        (before_sources if relative < 4 else after_sources).append(source)
    assert all(source is None for source in before_sources)
    assert "manual" in after_sources


def test_debris_report_context_event_reaches_pipeline(portable_root: Path) -> None:
    scenario = load_scenario("2024_qatar_mirror_debris", portable_root)
    assert scenario.metadata["context_events"] == [{
        "event": "Debris reported on track",
        "relative_time_s": 0.0,
        "quality": "REPORTED",
        "detail": "Mirror on main straight",
    }]
    before = next(f for f in scenario.frames
                  if scenario.relative_time(float(f["timestamp_s"].iloc[0])) == -5)
    at_zero = next(f for f in scenario.frames
                   if scenario.relative_time(float(f["timestamp_s"].iloc[0])) == 0)
    assert scenario.environment_at(before).debris_reported is None
    assert scenario.environment_at(at_zero).debris_reported is True


def test_new_scenario_replay_flag_ladders(portable_root: Path) -> None:
    target_flags = {
        "2024_azerbaijan_perez_sainz": ("RED_RECOMMENDED", 10.0),
        "2021_azerbaijan_verstappen": ("SAFETY_CAR", 10.0),
        "2022_canada_tsunoda": ("SAFETY_CAR", 10.0),
    }
    for scenario_id, (target_flag, deadline_s) in target_flags.items():
        folder = portable_root / scenario_id
        shutil.copy(SCENARIO_ROOT / scenario_id / "track.json", folder / "track.json")
        scenario = load_scenario(scenario_id, portable_root)
        results = scenario.replay()
        assert len(results) == len(scenario.frames)
        assert any(
            result.flag == target_flag
            and scenario.relative_time(result.timestamp_s) <= deadline_s
            for result in results
        )
        if scenario_id == "2022_canada_tsunoda":
            assert all(result.flag != "RED_RECOMMENDED" for result in results)

    qatar_folder = portable_root / "2024_qatar_mirror_debris"
    shutil.copy(SCENARIO_ROOT / "2024_qatar_mirror_debris" / "track.json", qatar_folder / "track.json")
    qatar = load_scenario("2024_qatar_mirror_debris", portable_root)
    qatar_results = qatar.replay()
    first_vsc = next(result for result in qatar_results if result.flag == "VSC")
    assert qatar.relative_time(first_vsc.timestamp_s) == pytest.approx(0.0)


def test_replay_prefix_is_causal_and_uses_normal_pipeline(portable_root: Path) -> None:
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    frames = scenario.frames[:45]
    first = SafetyPipeline(track=load_track(scenario.track_path))
    second = SafetyPipeline(track=load_track(scenario.track_path))
    first_results = [scenario.update_pipeline(first, frame) for frame in frames]
    second_results = [scenario.update_pipeline(second, frame) for frame in scenario.frames[:80]][:45]
    assert [(result.flag, result.severity, result.incident and result.incident["car_id"])
            for result in first_results] == [
                (result.flag, result.severity, result.incident and result.incident["car_id"])
                for result in second_results]
    assert [result.risk_score for result in first_results] == pytest.approx(
        [result.risk_score for result in second_results])
    assert first_results[0].flag == "GREEN"
    assert any(result.incident for result in first_results)
