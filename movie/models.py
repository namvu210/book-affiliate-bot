"""Data models for Movie Ad Generator."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Shot:
    """A single shot within a clip — describes one camera setup/beat."""
    timing: str  # e.g. "0-3s", "3-5s"
    framing: str  # extreme wide / wide / medium / close-up / extreme close-up / over-shoulder / POV
    camera_movement: str  # static / dolly in / dolly out / pan left / tilt up / tracking / crane / handheld
    action: str  # what happens in this beat (Vietnamese)
    lighting: str = ""  # e.g. "golden hour backlight", "neon rim light"
    transition: str = ""  # how this shot ends: cut / dissolve / whip pan / match cut


@dataclass
class Clip:
    """One 8-second Veo 3 clip, described as a sequence of shots."""
    clip_number: int  # 1 or 2
    shots: list[Shot] = field(default_factory=list)
    motion_prompt: str = ""  # synthesized EN prompt for Veo 3
    dialogue: Optional[str] = None
    mood: str = ""  # emotional tone: tense / playful / dreamy / energetic
    key_frame_description: str = ""  # description of the start frame for image generation


@dataclass
class MovieScreenplay:
    title: str
    story_hook: str
    clips: list[Clip] = field(default_factory=list)
    product_placement: str = ""
    kol_ids: list[str] = field(default_factory=list)
    cinematic_style: str = ""  # e.g. "Wong Kar-wai neon noir", "Wes Anderson symmetry"


@dataclass
class MovieProject:
    id: str
    product_title: str
    product_url: Optional[str] = None
    product_images: list[str] = field(default_factory=list)
    kol_ids: list[str] = field(default_factory=list)
    screenplay: Optional[dict] = None
    scene_images: list[str] = field(default_factory=list)
    video_clips: list[str] = field(default_factory=list)
    final_video: Optional[str] = None
    narration_path: Optional[str] = None
    status: str = "draft"
    created_at: str = ""
