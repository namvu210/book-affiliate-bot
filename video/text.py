"""Text utilities for video generation."""

import re
from pathlib import Path

from PIL import ImageDraw, ImageFont


def get_font(size: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    if bold:
        paths.insert(0, "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        paths.insert(1, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for w in words[1:]:
            test = current + " " + w
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = w
        lines.append(current)
    return lines


def split_sentences(text: str) -> list[str]:
    text = re.sub(r'\[[^\]]*\]', '', text)
    parts = re.split(r'(?<=[.!?。])\s+', text.strip())
    sentences = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > 60:
            subs = re.split(r'(?<=[,;:\n])\s+|(?<=\s[-–])\s+', p)
            sentences.extend(s.strip() for s in subs if s.strip())
        else:
            sentences.append(p)
    final = []
    for s in sentences:
        if len(s) > 80:
            words = s.split()
            mid = len(words) // 2
            final.append(" ".join(words[:mid]))
            final.append(" ".join(words[mid:]))
        else:
            final.append(s)
    return final or [text]
