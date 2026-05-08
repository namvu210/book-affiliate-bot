"""Text-to-speech: gTTS (fast) or ElevenLabs (expressive)."""

import re
import subprocess
from pathlib import Path

from gtts import gTTS

from config import strip_emoji, get_audio_duration, DEFAULT_VOICE_SPEED

VOICE_DIR = Path(__file__).parent / "voices"
VOICE_DIR.mkdir(exist_ok=True)


def _sanitize(text: str, keep_audio_tags: bool = False) -> str:
    text = re.sub(r'\[\d+[-–]\d+s?\]', '', text)  # strip timestamps [0-3s]
    if not keep_audio_tags:
        text = re.sub(r'\[[a-zA-Z_ ]+\]', '', text)  # strip audio tags [excited] for gTTS
    text = strip_emoji(text)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(?:www\.|\w+\.(?:com|vn|net|org|io|dev|co))\S*', '', text)  # bare URLs
    text = re.sub(r'[*_~`]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:5000]


def _apply_speed(path: str, speed: int):
    """Apply tempo change to audio file in-place. speed=100 means no change."""
    if speed == 100:
        return
    tempo = speed / 100
    tmp = path + ".spd.mp3"
    filters = []
    t = tempo
    while t > 2.0:
        filters.append("atempo=2.0")
        t /= 2.0
    while t < 0.5:
        filters.append("atempo=0.5")
        t /= 0.5
    filters.append(f"atempo={t:.4f}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-filter:a", ",".join(filters), tmp],
        capture_output=True, timeout=30,
    )
    if Path(tmp).exists():
        Path(tmp).replace(path)


async def generate_audio(
    text: str,
    output_path: str,
    speed: int = DEFAULT_VOICE_SPEED,
    voice_type: str = "edge",
    elevenlabs_voice_id: str = "",
    edge_voice: str = "vi-VN-HoaiMyNeural",
    # deprecated — ignored, use speed instead
    rate: str = "",
) -> str:
    """Generate speech audio. speed=100 is normal, 175 is 1.75x."""
    clean = _sanitize(text, keep_audio_tags=(voice_type in ("elevenlabs", "edge")))
    if not clean:
        return ""

    if voice_type == "elevenlabs":
        try:
            await _generate_elevenlabs(clean, output_path, elevenlabs_voice_id)
        except Exception as e:
            import logging
            logging.getLogger("tts").warning(f"ElevenLabs failed, falling back to Edge TTS: {e}")
            await _generate_edge(_sanitize(text, keep_audio_tags=True), output_path, edge_voice)
    elif voice_type == "edge":
        await _generate_edge(clean, output_path, edge_voice)
    else:
        await _generate_gtts(clean, output_path)

    _apply_speed(output_path, speed)

    if not Path(output_path).exists():
        raise RuntimeError("TTS failed: no audio generated")
    return output_path


async def _generate_gtts(text: str, output_path: str) -> str:
    """Generate raw gTTS audio at normal speed."""
    tts = gTTS(text=text, lang="vi", slow=False)
    tts.save(output_path)
    return output_path


def _tags_to_edge_text(text: str) -> str:
    """Convert ElevenLabs audio tags to natural pauses for Edge TTS."""
    import re
    # Non-verbal tags → ellipsis pause
    pause_tags = ['sighs', 'laughs', 'gasps', 'chuckles', 'exhales', 'snorts',
                  'short pause', 'long pause', 'inhales deeply', 'exhales sharply', 'clears throat']
    for tag in pause_tags:
        text = re.sub(rf'\[{tag}\]', ' ... ', text, flags=re.IGNORECASE)

    # Emotion tags → brief pause
    emotion_tags = ['excited', 'surprised', 'curious', 'happy', 'thoughtful',
                    'whispers', 'sarcastic', 'mischievously', 'angry', 'sad', 'annoyed']
    for tag in emotion_tags:
        text = re.sub(rf'\[{tag}\]', ' — ', text, flags=re.IGNORECASE)

    # Strip any remaining [tags]
    text = re.sub(r'\[[a-zA-Z_ ]+\]', '', text)

    # Fix ALL CAPS words (>2 chars) → Title Case to prevent letter-by-letter spelling
    def _fix_caps(m):
        w = m.group(0)
        if len(w) <= 2:  # keep OK, AI, etc as-is
            return w
        return w.capitalize()
    text = re.sub(r'\b[A-Z][A-Z.]{2,}\b', _fix_caps, text)

    # Fix brand names with dots (MACS.OUTFIT → Macs Outfit)
    text = re.sub(r'(\w)\.(\w)', r'\1 \2', text)

    text = re.sub(r'  +', ' ', text).strip()
    return text


async def _generate_edge(text: str, output_path: str, voice: str = "vi-VN-HoaiMyNeural") -> str:
    """Generate speech using Microsoft Edge TTS (free, unlimited)."""
    import edge_tts
    clean = _tags_to_edge_text(text)
    communicate = edge_tts.Communicate(clean, voice)
    await communicate.save(output_path)
    return output_path


async def _generate_elevenlabs(text: str, output_path: str, voice_id_override: str = "") -> str:
    """Generate speech using ElevenLabs."""
    import os
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = (voice_id_override.strip() if voice_id_override else "") or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if not api_key or not voice_id:
        raise RuntimeError("Cần ELEVENLABS_API_KEY và ELEVENLABS_VOICE_ID trong .env")

    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_v3",
        output_format="mp3_44100_128",
        language_code="vi",
    )
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    return output_path


def save_voice_sample(data: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    raw_path = VOICE_DIR / f"my-voice{ext}"
    raw_path.write_bytes(data)
    wav_path = VOICE_DIR / "my-voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "5", "-i", str(raw_path), "-ar", "24000", "-ac", "1", "-t", "10", str(wav_path)],
        capture_output=True, timeout=30,
    )
    if wav_path.exists():
        return str(wav_path)
    raise RuntimeError("Không thể xử lý file giọng nói")


def get_voice_sample() -> str | None:
    wav = VOICE_DIR / "my-voice.wav"
    return str(wav) if wav.exists() else None
