from pathlib import Path

from config import Config
from src.pipeline import AnalysisResult, SafetyPipeline
from src.telemetry import load_telemetry


def replay(csv_path: Path, pipeline: SafetyPipeline) -> list[AnalysisResult]:
    return [pipeline.update(frame) for frame in load_telemetry(csv_path)]


if __name__ == "__main__":
    config = Config()
    previous_flag = None
    for result in replay(config.demo_path, SafetyPipeline(config)):
        if result.flag != previous_flag:
            print(
                f"{result.timestamp_s:05.1f}s  {result.flag or result.status}"
                f"  car={result.incident['car_id'] if result.incident else '-'}"
                f"  risk={result.risk_score:.2f}"
            )
            previous_flag = result.flag
