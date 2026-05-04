"""Tests for batch mode pipeline behaviors."""
import pytest
from unittest.mock import patch, MagicMock


def test_review_error_does_not_leak_to_social_post():
    """When Gemini fails, social_post must be empty — never contain error messages."""
    from reviewer import generate_review
    from extractor import BookInfo

    book = BookInfo(title="Test Product", author="", description="A test product")
    with patch("reviewer.generate_json", side_effect=RuntimeError("503 UNAVAILABLE. This model is experiencing high demand.")):
        result = generate_review(book, "phu-huynh-lop-5", "facebook")

    assert result["social_post"] == "", f"social_post should be empty on error, got: {result['social_post'][:50]}"
    assert "503" in result["review"], "error should be in review field for debugging"


def test_review_error_keeps_all_fallback_fields():
    """Failed review should have all expected fields with safe defaults."""
    from reviewer import generate_review
    from extractor import BookInfo

    book = BookInfo(title="Test", author="", description="")
    with patch("reviewer.generate_json", side_effect=RuntimeError("API error")):
        result = generate_review(book, "phu-huynh-lop-5", "tiktok")

    assert "social_post" in result
    assert "hashtags" in result
    assert "hook" in result
    assert "key_points" in result
    assert "cta" in result
    assert isinstance(result["hashtags"], list)
    assert isinstance(result["key_points"], list)


@pytest.mark.asyncio
async def test_process_product_skips_unselected_platforms():
    """Only selected platforms should have reviews generated."""
    from pipeline import PipelineInput, process_product
    from extractor import BookInfo

    mock_review = {"social_post": "test post", "review": "test", "hashtags": [], "hook": "", "key_points": [], "cta": ""}
    with patch("pipeline.extract_from_shopee", return_value=BookInfo(title="Test", author="", description="A product", shopee_url="https://shopee.vn/test")), \
         patch("pipeline.get_affiliate_link", return_value=""), \
         patch("reviewer.generate_review", return_value=mock_review), \
         patch("tts.generate_audio", return_value=""), \
         patch("pipeline._resolve_images", return_value=[]), \
         patch("imagegen.generate_lifestyle_images", return_value=[]):

        inp = PipelineInput(url="https://shopee.vn/test-i.1.2", platforms=["facebook"])
        result = await process_product(inp)

        assert "facebook" in result.review_data, "facebook should be generated"
        assert "tiktok" not in result.review_data, "tiktok should be skipped"


@pytest.mark.asyncio
async def test_render_video_rejects_empty_social_post():
    """Video render should return error when social_post is empty."""
    from video.prepare import VideoInput, render_video

    inp = VideoInput(review_data={"book": {"title": "Test"}, "facebook": {"social_post": "", "audio_url": ""}}, platform="facebook")
    result = await render_video(inp)
    assert "error" in result


@pytest.mark.asyncio
async def test_render_video_rejects_missing_audio():
    """Video render should return error when audio file doesn't exist."""
    from video.prepare import VideoInput, render_video

    inp = VideoInput(review_data={"book": {"title": "Test"}, "facebook": {"social_post": "Some content", "audio_url": "/output/nonexistent.mp3"}}, platform="facebook")
    result = await render_video(inp)
    assert "error" in result


def test_build_post_request_extracts_affiliate():
    """Affiliate link should come from book.shopee_url."""
    from poster import build_post_request

    data = {"book": {"title": "Test", "shopee_url": "https://s.shopee.vn/abc"}, "facebook": {"social_post": "review text", "hashtags": ["tag1"]}}
    req = build_post_request(data, "/output/test.mp4", "facebook")
    assert req.affiliate_link == "https://s.shopee.vn/abc"


def test_build_post_request_empty_affiliate():
    """No affiliate link when book has no shopee_url."""
    from poster import build_post_request

    data = {"book": {"title": "Test"}, "facebook": {"social_post": "review", "hashtags": []}}
    req = build_post_request(data, "/output/test.mp4", "facebook")
    assert req.affiliate_link == ""
