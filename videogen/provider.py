"""Abstract provider interface for image-to-video generation."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from config import log


@dataclass
class VideoClipRequest:
    """Input for a single image-to-video generation."""
    image_path: str
    motion_prompt: str
    duration_s: float = 4.0
    aspect_ratio: str = "9:16"


@dataclass
class VideoClipResult:
    """Result of a single clip generation."""
    video_path: str | None = None
    error: str | None = None
    duration_s: float = 0.0


class VideoGenProvider(ABC):
    """Base class for image-to-video providers."""

    name: str = "base"

    @abstractmethod
    async def generate_clip(self, request: VideoClipRequest, output_path: str) -> VideoClipResult:
        """Generate a video clip from an image + motion prompt."""
        ...

    async def generate_clips(self, requests: list[VideoClipRequest], output_dir: str) -> list[VideoClipResult]:
        """Generate multiple clips. Override for batch-optimized providers."""
        results = []
        for i, req in enumerate(requests):
            out = str(Path(output_dir) / f"clip_{i}.mp4")
            result = await self.generate_clip(req, out)
            results.append(result)
        return results


_provider: VideoGenProvider | None = None


def get_provider() -> VideoGenProvider:
    """Get the configured video generation provider."""
    global _provider
    if _provider is None:
        from videogen.mock import MockProvider
        _provider = MockProvider()
        log.info(f"VideoGen provider: {_provider.name}")
    return _provider


def set_provider(provider: VideoGenProvider):
    """Set the active video generation provider."""
    global _provider
    _provider = provider
    log.info(f"VideoGen provider set: {provider.name}")
