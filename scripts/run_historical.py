"""Headless historical replay using the same pipeline as Streamlit."""

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.historical import load_scenario, scenario_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=scenario_ids(), required=True)
    parser.add_argument("--write-derived", action="store_true")
    args = parser.parse_args()
    scenario = load_scenario(args.scenario)
    print(scenario.metadata["title"], "|", scenario.metadata["data_quality"])
    print("ACTUAL — documented control actions")
    for action in scenario.metadata["actual_control_actions"]:
        when = action["relative_time_s"]
        print(f"  T={when:+.1f}s" if when is not None else "  T=unknown", action["action"], f"[{action['timing_quality']}]")
    print("FLAGSENSE — pipeline transitions")
    results = scenario.replay()
    previous = None
    for result in results:
        if result.flag != previous:
            t = scenario.relative_time(result.timestamp_s)
            print(f"  T={t:+.1f}s {result.flag or result.status} risk={result.risk_score:.2f} severity={result.severity} rule={result.rule_id}")
            previous = result.flag
    if args.write_derived:
        rows = [{
            "timestamp_s": r.timestamp_s,
            "relative_time_s": scenario.relative_time(r.timestamp_s),
            "recommendation": r.flag,
            "severity": r.severity,
            "severity_index": r.risk_score,
            "rule_id": r.rule_id,
            "incident_car_id": r.incident["car_id"] if r.incident else None,
            "origin": "DERIVED_FROM_NORMAL_PIPELINE",
        } for r in results]
        output = scenario.path / "derived_features.csv"
        pd.DataFrame(rows).to_csv(output, index=False)
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
