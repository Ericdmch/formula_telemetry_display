from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.historical import load_scenario


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_dashboard_loads_offline_demo_and_controls_playback() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value == "FlagSense"
    assert at.session_state["latest_result"].flag == "GREEN"
    assert at.session_state["playback_index"] == 0

    at.get_by_key("start_demo").click().run()
    assert at.session_state["running"] is True

    at.get_by_key("pause_demo").click().run()
    assert at.session_state["running"] is False

    at.get_by_key("reset_demo").click().run()
    assert at.session_state["playback_index"] == 0
    assert at.session_state["latest_result"].flag == "GREEN"


def test_dashboard_can_select_historical_case_without_network() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.get_by_key("scenario_choice").set_value("2024_qatar_mirror_debris").run()

    assert not at.exception
    assert at.session_state["active_scenario"] == "2024_qatar_mirror_debris"
    assert at.session_state["latest_result"].status == "OK"
    assert any("Actual race control vs FlagSense" in item.value for item in at.subheader)
    assert at.session_state["playback_index"] == 0


def test_dashboard_displays_first_measured_or_fallback_replay() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.get_by_key("scenario_choice").set_value("2024_azerbaijan_perez_sainz").run()

    assert not at.exception
    assert at.session_state["active_scenario"] == "2024_azerbaijan_perez_sainz"
    assert at.session_state["latest_result"].flag == "GREEN"
    assert any("Actual race control vs FlagSense" in item.value for item in at.subheader)
    assert any("Data quality" in item.value for item in at.info)


def test_historical_incident_shows_recorded_still_in_main_card_without_pausing() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.get_by_key("scenario_choice").set_value("2024_qatar_mirror_debris").run()
    assert any("appears at T=0" in item.value for item in at.main.caption)
    assert not any(item.type == "image" for item in at.main)
    at.get_by_key("speed_multiplier").set_value(4).run()
    scenario = load_scenario("2024_qatar_mirror_debris")
    onset_frame = next(index for index, frame in enumerate(scenario.frames)
                       if scenario.relative_time(float(frame["timestamp_s"].iloc[0])) >= 0)
    at.session_state["playback_index"] = onset_frame - 0.5
    at.session_state["running"] = True
    at.run()

    assert not at.exception
    assert at.session_state["running"] is True
    assert at.session_state["playback_index"] > onset_frame
    assert at.session_state["latest_result"].context_evidence["vision_source"] == "cached"
    assert any("fragment is visible" in reason for reason in at.session_state["latest_result"].reasons)
    assert any(item.type == "image" for item in at.main)
    assert any("small dark fragment" in item.value.lower() for item in at.main.markdown)
    assert not any("Why this recommendation?" in item.value for item in at.main.markdown)
    assert not any(button.key == "continue_after_incident" for button in at.button)

    at.get_by_key("reset_demo").click().run()
    assert not any(item.type == "image" for item in at.main)
