"""Optional still-image adapter; no image model is bundled with the offline demo."""

from typing import Callable

from src.sensor_fusion import VisualFeatures


class VisionAnalyzer:
    """A configured provider returns observable facts, never a recommendation."""

    def __init__(self, provider: Callable[[bytes], VisualFeatures | None] | None = None):
        self.provider = provider

    def analyze(self, image: bytes) -> VisualFeatures | None:
        if not image:
            raise ValueError("empty image")
        return self.provider(image) if self.provider is not None else None
