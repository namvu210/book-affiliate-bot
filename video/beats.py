"""Beat detection using ffmpeg + numpy. No external dependencies beyond numpy."""

import json
import subprocess
from pathlib import Path

import numpy as np

_cache: dict[str, list[float]] = {}
CACHE_DIR = Path(__file__).parent.parent / "music" / ".beats"


def detect_beats(music_path: str, min_interval: float = 0.35) -> list[float]:
    """Detect beat timestamps in an audio file. Returns list of seconds. Cached per file."""
    if music_path in _cache:
        return _cache[music_path]

    # Check disk cache
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / (Path(music_path).stem + ".json")
    if cache_file.exists():
        beats = json.loads(cache_file.read_text())
        _cache[music_path] = beats
        return beats

    # Decode to raw PCM via ffmpeg
    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", music_path, "-ac", "1", "-ar", "22050", "-f", "s16le", "-"],
            capture_output=True, timeout=10,
        )
        if proc.returncode != 0:
            return []
        raw = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    except Exception:
        return []

    if len(raw) < 22050:
        return []

    sr = 22050
    # Compute energy in short windows
    hop = int(sr * 0.01)  # 10ms hops
    win = int(sr * 0.04)  # 40ms window
    energy = np.array([np.sum(raw[i:i+win] ** 2) for i in range(0, len(raw) - win, hop)])

    if len(energy) < 10:
        return []

    # Normalize
    energy = energy / (np.max(energy) + 1e-10)

    # Onset detection: find peaks where energy rises sharply
    diff = np.diff(energy)
    diff = np.maximum(diff, 0)  # only positive changes (onsets)

    # Adaptive threshold: mean + 1.5 * std of positive diffs
    threshold = np.mean(diff) + 1.5 * np.std(diff)
    peaks = np.where(diff > threshold)[0]

    # Convert to seconds and enforce minimum interval
    beats = []
    last = -min_interval
    for p in peaks:
        t = float(p * hop / sr)
        if t - last >= min_interval:
            beats.append(round(t, 3))
            last = t

    # Cache to disk
    cache_file.write_text(json.dumps(beats))
    _cache[music_path] = beats
    return beats
