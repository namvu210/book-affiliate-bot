import os
import re
from datetime import datetime
from pathlib import Path

# Google Gemini config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Upload
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

_EMOJI_RE = re.compile(
    r'[\U0001f000-\U0001ffff\U00002702-\U000027B0\U0000fe00-\U0000fe0f'
    r'\U0001fa00-\U0001faff\U00002600-\U000026FF\U0000200d\U00002640'
    r'\U00002642\U00002b50\U00002b55\U00002934-\U00002935'
    r'\U00002b05-\U00002b07\U0000231a-\U0000231b\U000023e9-\U000023fa'
    r'\U000025aa-\U000025fe\U00003030\U0000303d\U00003297\U00003299]+'
)


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub('', text).strip()


def make_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def output_path(ts: str, suffix: str) -> Path:
    """Build OUTPUT_DIR/ts_suffix and create parent dirs."""
    p = Path(OUTPUT_DIR) / f"{ts}_{suffix}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def output_url(ts: str, suffix: str) -> str:
    return f"/output/{ts}_{suffix}"


def get_audio_duration(path: str) -> float | None:
    """Get duration of an audio/video file via ffprobe."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return None

# Voice
DEFAULT_VOICE_SPEED = 120

# AffiPad
AFFIPAD_API_KEY = os.getenv("AFFIPAD_API_KEY", "")
AFFIPAD_TOOL_ID = os.getenv("AFFIPAD_TOOL_ID", "")

# Target audience templates
AUDIENCES = {
    "phu-huynh-lop-5": {
        "name": "Phụ huynh có con lớp 5",
        "tone": "thân thiện, dễ hiểu, như một người bạn đồng hành cùng con",
        "focus": "giá trị giáo dục, phù hợp lứa tuổi, giúp con học tốt hơn",
    },
    "phu-huynh-mam-non": {
        "name": "Phụ huynh có con mầm non",
        "tone": "nhẹ nhàng, ấm áp, khuyến khích đọc sách cùng con",
        "focus": "hình ảnh đẹp, kích thích trí tưởng tượng, phát triển ngôn ngữ",
    },
    "hoc-sinh-thpt": {
        "name": "Học sinh THPT",
        "tone": "năng động, truyền cảm hứng, gần gũi gen Z",
        "focus": "kỹ năng sống, định hướng nghề nghiệp, phát triển bản thân",
    },
}
