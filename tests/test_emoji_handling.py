"""Test that emojis in review text are handled correctly in each path."""
import sys
sys.path.insert(0, ".")

from config import strip_emoji
from tts import _sanitize, _tags_to_edge_text
from poster import _build_caption, PostRequest


SAMPLE_TEXT = "[excited] Mọi người ơi 💖 sản phẩm này ĐỈNH luôn! 😍 [laughs] Chất liệu mềm mại… cực kỳ thoải mái ✨ https://s.shopee.vn/abc123"


def test_tts_strips_emojis_and_tags():
    """TTS should strip emojis, audio tags, and URLs — only clean Vietnamese text remains."""
    result = _sanitize(SAMPLE_TEXT, keep_audio_tags=False)
    assert "💖" not in result, "Emoji should be stripped for TTS"
    assert "😍" not in result
    assert "✨" not in result
    assert "[excited]" not in result, "Audio tags should be stripped"
    assert "[laughs]" not in result
    assert "https" not in result, "URLs should be stripped"
    assert "shopee" not in result, "Bare URLs should be stripped"
    assert "ĐỈNH" in result, "Vietnamese text should remain"
    assert "thoải mái" in result


def test_tts_keeps_tags_for_elevenlabs():
    """ElevenLabs TTS should keep audio tags but strip emojis and URLs."""
    result = _sanitize(SAMPLE_TEXT, keep_audio_tags=True)
    assert "[excited]" in result, "Audio tags kept for ElevenLabs"
    assert "[laughs]" in result
    assert "💖" not in result, "Emojis still stripped for TTS"
    assert "https" not in result, "URLs still stripped"


def test_edge_tts_converts_tags_to_pauses():
    """Edge TTS should convert audio tags to natural pauses."""
    result = _tags_to_edge_text("[excited] Hello [sighs] world")
    assert "[excited]" not in result
    assert "[sighs]" not in result
    assert "—" in result or "..." in result, "Tags should become pauses"
    assert "Hello" in result
    assert "world" in result


def test_caption_strips_tags_keeps_emojis():
    """Caption for social media should strip audio tags but keep emojis and line breaks."""
    req = PostRequest(
        video_path="test.mp4",
        caption="[excited] Mọi người ơi 💖 sản phẩm này ĐỈNH! 😍\n\n[laughs] Mua ngay nha!",
        hashtags=["review", "shopee"],
        title="Test",
        affiliate_link="https://s.shopee.vn/abc",
    )
    result = _build_caption(req)
    assert "💖" in result, "Emojis should be preserved in caption"
    assert "😍" in result
    assert "\n" in result, "Line breaks should be preserved"
    assert "[excited]" not in result, "Audio tags should be stripped"
    assert "[laughs]" not in result
    assert "#review" in result, "Hashtags should be appended"
    assert "https://s.shopee.vn/abc" in result, "Affiliate link should be appended"


def test_video_text_strips_emojis():
    """Video text overlay should not contain emojis."""
    text = "Sản phẩm này 💖 rất tốt 😍 luôn!"
    result = strip_emoji(text)
    assert "💖" not in result
    assert "😍" not in result
    assert "rất tốt" in result


def test_edge_tts_fixes_caps_brand():
    """Edge TTS should convert ALL CAPS brand names to title case."""
    result = _tags_to_edge_text("MACS.OUTFIT VIAN SHIRT rất đẹp")
    assert "MACS" not in result, "ALL CAPS should be converted"
    assert "Macs" in result or "macs" in result
    assert "." not in result.split("VIAN")[0] if "VIAN" in result else True, "Dots in brand should become spaces"


if __name__ == "__main__":
    test_tts_strips_emojis_and_tags()
    test_tts_keeps_tags_for_elevenlabs()
    test_edge_tts_converts_tags_to_pauses()
    test_caption_strips_tags_keeps_emojis()
    test_video_text_strips_emojis()
    test_edge_tts_fixes_caps_brand()
    print("✅ All 6 tests passed")
