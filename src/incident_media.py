"""Reviewed visual evidence for the four user-supplied replay stills.

The descriptions are assembled from observations tied to exact image hashes.
This is an offline evidence cache, not a general-purpose image classifier.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from src.sensor_fusion import VisualFeatures


@dataclass(frozen=True)
class IncidentStill:
    image_path: Path
    available_at_relative_s: float
    scene: str
    visible_details: tuple[str, ...]
    features: VisualFeatures


def load_incident_still(scenario_path: Path) -> IncidentStill | None:
    """Load a still only when its reviewed facts match the supplied image."""
    manifest = scenario_path / "visual_features.json"
    if not manifest.is_file():
        return None
    raw = json.loads(manifest.read_text())
    image_file = raw.get("image_file")
    if image_file is None:
        return None  # Older evidence-only caches have no display image.
    if (not isinstance(image_file, str) or image_file in (".", "..")
            or Path(image_file).name != image_file):
        raise ValueError("incident image must be a filename in the scenario folder")
    image_path = scenario_path / image_file
    actual_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    if actual_hash != raw.get("image_sha256"):
        raise ValueError("incident image does not match reviewed visual facts")
    scene = raw.get("scene")
    details = raw.get("visible_details")
    if not isinstance(scene, str) or not scene.strip():
        raise ValueError("incident scene observation required")
    if not isinstance(details, list) or not all(
        isinstance(item, str) and item.strip() for item in details
    ):
        raise ValueError("incident visible details must be nonempty strings")
    features = VisualFeatures(**raw["features"])
    if features.source != "cached":
        raise ValueError("bundled incident observations must be cached evidence")
    return IncidentStill(
        image_path=image_path,
        available_at_relative_s=float(raw["available_at_relative_s"]),
        scene=scene.strip(),
        visible_details=tuple(item.strip() for item in details),
        features=features,
    )


def describe_incident_still(still: IncidentStill) -> str:
    """Turn reviewed, visible observations into a restrained scene description."""
    return " ".join((still.scene, *still.visible_details))
