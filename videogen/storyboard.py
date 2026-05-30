"""Storyboard: split a 15s ad script into scenes with motion prompts."""

import json

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, log

SCENE_MODEL = "gemini-2.5-flash-lite"


def generate_storyboard(
    ad_script: str,
    product_title: str,
    persona_name: str = "",
    num_clips: int = 4,
) -> list[dict]:
    """Generate a storyboard: split ad_script into scenes with motion direction.

    Returns list of {"text": str, "motion": str, "duration_s": float}.
    Each motion prompt describes camera/subject movement for image-to-video.
    """
    prompt = (
        f"You are a TikTok ad creative director. Split this 15-second Vietnamese ad script "
        f"into {num_clips} video scenes with motion direction for each.\n\n"
        f"Product: {product_title}\n"
        f"Target: {persona_name or 'general'}\n"
        f"Script: {ad_script}\n\n"
        f"For each scene, provide:\n"
        f"- text: the narration for that scene (subset of the script)\n"
        f"- motion: camera/subject movement description for image-to-video generation "
        f"(e.g., 'slow zoom in on face, gentle head turn left, soft smile', "
        f"'camera pulls back revealing full outfit, wind blows hair', "
        f"'close-up hand picks up product, brings to face'). Under 30 words.\n"
        f"- duration_s: how long this clip should be (total must equal 15)\n\n"
        f"RULES:\n"
        f"- First scene: attention-grabbing motion (fast zoom, dramatic reveal)\n"
        f"- Last scene: slow down, product visible, CTA moment\n"
        f"- Vary motion types: zoom, pan, tilt, subject movement, camera orbit\n"
        f"- Keep motions physically plausible (no teleportation)\n"
        f"- Motion must match what a 3-5 second clip can show\n\n"
        f"Return JSON array: [{{\"text\": ..., \"motion\": ..., \"duration_s\": ...}}, ...]"
    )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=SCENE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                max_output_tokens=600,
                response_mime_type="application/json",
            ),
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        scenes = json.loads(text)
        if isinstance(scenes, dict):
            scenes = scenes.get("scenes", scenes.get("storyboard", []))
        if not isinstance(scenes, list):
            raise ValueError(f"Expected list, got {type(scenes)}")
        result = []
        for s in scenes[:num_clips]:
            result.append({
                "text": s.get("text", ""),
                "motion": s.get("motion", "subtle cinematic movement"),
                "duration_s": float(s.get("duration_s", 15 / num_clips)),
            })
        # Normalize durations to sum to 15
        total = sum(s["duration_s"] for s in result)
        if total > 0 and abs(total - 15) > 0.5:
            for s in result:
                s["duration_s"] = round(s["duration_s"] / total * 15, 1)
        log.info(f"Storyboard: {len(result)} scenes, durations={[s['duration_s'] for s in result]}")
        return result
    except Exception as e:
        log.warning(f"Storyboard generation failed: {e}")
        # Fallback: split script evenly
        words = ad_script.split()
        per_scene = max(1, len(words) // num_clips)
        result = []
        for i in range(num_clips):
            chunk = " ".join(words[i * per_scene:(i + 1) * per_scene])
            if not chunk and i == num_clips - 1:
                chunk = words[-1] if words else ""
            result.append({
                "text": chunk,
                "motion": "subtle cinematic movement, gentle zoom",
                "duration_s": round(15 / num_clips, 1),
            })
        return [s for s in result if s["text"]]
