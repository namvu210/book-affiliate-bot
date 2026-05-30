"""Tests for videogen module."""

import sys
sys.path.insert(0, ".")

import asyncio
from unittest.mock import patch, MagicMock
from videogen.provider import VideoClipRequest, VideoClipResult
from videogen.storyboard import generate_storyboard
from video.prepare import pick_effect_combo


def test_pick_effect_combo_from_provider():
    """pick_effect_combo is importable from provider module."""
    from video.prepare import pick_effect_combo, _INCOMPATIBLE, EFFECT_POOL, STYLE_POOL
    # Deterministic
    e1, s1 = pick_effect_combo(seed=99)
    e2, s2 = pick_effect_combo(seed=99)
    assert (e1, s1) == (e2, s2)
    # Valid values
    assert e1 in EFFECT_POOL
    assert s1 in STYLE_POOL
    # Not incompatible
    blocked = _INCOMPATIBLE.get(e1, set())
    assert s1 not in blocked


def test_storyboard_fallback():
    """Storyboard returns fallback scenes when LLM fails."""
    with patch("videogen.storyboard.genai") as mock_genai:
        mock_genai.Client.side_effect = Exception("API down")
        scenes = generate_storyboard(
            ad_script="Kem chống nắng siêu nhẹ, bảo vệ da cả ngày. Mua ngay!",
            product_title="L'Oréal UV Defender",
            num_clips=3,
        )
    assert len(scenes) > 0
    assert all("text" in s and "motion" in s and "duration_s" in s for s in scenes)
    total_dur = sum(s["duration_s"] for s in scenes)
    assert abs(total_dur - 15) < 1.0


def test_video_clip_request_dataclass():
    """VideoClipRequest holds correct fields."""
    req = VideoClipRequest(
        image_path="/tmp/test.png",
        motion_prompt="slow zoom in, gentle smile",
        duration_s=4.0,
        aspect_ratio="9:16",
    )
    assert req.image_path == "/tmp/test.png"
    assert req.duration_s == 4.0


def test_mock_provider_missing_image():
    """MockProvider returns error for missing image."""
    from videogen.mock import MockProvider
    provider = MockProvider()
    req = VideoClipRequest(
        image_path="/nonexistent/image.png",
        motion_prompt="zoom in",
        duration_s=3.0,
    )
    result = asyncio.run(provider.generate_clip(req, "/tmp/out.mp4"))
    assert result.error is not None
    assert "not found" in result.error.lower()


def test_generate_ad_creative_no_images():
    """generate_ad_creative returns error without images."""
    from videogen.compose import generate_ad_creative
    result = asyncio.run(generate_ad_creative(
        product_title="Test",
        ad_script="Some script here",
        ai_image_paths=[],
    ))
    assert result.get("error")
    assert "No AI images" in result["error"]


def test_generate_ad_creative_no_script():
    """generate_ad_creative returns error without script."""
    from videogen.compose import generate_ad_creative
    result = asyncio.run(generate_ad_creative(
        product_title="Test",
        ad_script="",
        ai_image_paths=["/tmp/img.png"],
    ))
    assert result.get("error")
    assert "No ad script" in result["error"]
