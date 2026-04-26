"""Text-to-speech using gTTS (free, supports Vietnamese)."""

import re
import subprocess
from pathlib import Path
from gtts import gTTS


def _sanitize(text: str) -> str:
    """Clean text for TTS - remove timestamps, emoji, hashtags, URLs."""
    text = re.sub(r'\[\d+[-–]\d+s?\]', '', text)
    text = re.sub(r'[\U0001f000-\U0001ffff\U00002702-\U000027B0\U0000fe00-\U0000fe0f\U0001fa00-\U0001faff\U00002600-\U000026FF]+', '', text)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[*_~`]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:2000]


async def generate_audio(
    text: str,
    output_path: str,
    rate: str = "+75%",
) -> str:
    """Generate MP3 audio from Vietnamese text."""
    clean = _sanitize(text)
    if not clean:
        return ""

    tmp_path = output_path + ".tmp.mp3"
    tts = gTTS(text=clean, lang="vi", slow=False)
    tts.save(tmp_path)

    # Speed up with ffmpeg atempo filter
    pct = int(re.search(r'\d+', rate).group()) if re.search(r'\d+', rate) else 0
    tempo = 1 + pct / 100 if pct > 0 else 1.0
    subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_path, "-filter:a", f"atempo={tempo}", output_path],
        capture_output=True, timeout=30,
    )
    Path(tmp_path).unlink(missing_ok=True)

    # If over 30s, speed up further to fit under 30s
    MAX_DURATION = 30.0
    duration = _get_duration(output_path)
    if duration and duration > MAX_DURATION:
        extra_tempo = duration / MAX_DURATION
        tmp2 = output_path + ".fast.mp3"
        # atempo only accepts 0.5-2.0, chain filters if needed
        filters = []
        t = extra_tempo
        while t > 2.0:
            filters.append("atempo=2.0")
            t /= 2.0
        filters.append(f"atempo={t:.4f}")
        subprocess.run(
            ["ffmpeg", "-y", "-i", output_path, "-filter:a", ",".join(filters), tmp2],
            capture_output=True, timeout=30,
        )
        if Path(tmp2).exists():
            Path(tmp2).replace(output_path)

    if not Path(output_path).exists():
        raise RuntimeError("TTS failed: no audio generated")

    return output_path


def _get_duration(path: str) -> float | None:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
