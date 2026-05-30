"""Screenplay generation for Movie Ads using Gemini — shot-level cinematic breakdowns."""

import json
import time
import yaml
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY, log
from imagegen import _resize_for_input
import kol_manager

PROMPT_PATH = Path("prompts/movie_screenplay.yaml")

STORY_STYLES = {
    "heist": "Nhân vật 'đánh cắp' hoặc lén lấy sản phẩm như phim trộm — suspense, nhịp nhanh",
    "time_loop": "Nhân vật bị kẹt lặp lại 1 khoảnh khắc cho đến khi dùng sản phẩm — absurd, hài",
    "wrong_genre": "Bắt đầu như 1 thể loại (romance/action/drama) rồi bẻ lái sang quảng cáo — bất ngờ",
    "reverse": "Kể ngược từ kết quả về nguyên nhân — mở đầu bằng khoảnh khắc đỉnh điểm",
    "pov_object": "Kể từ góc nhìn của sản phẩm — sản phẩm là narrator/nhân vật chính",
    "one_take_chaos": "Giả lập one-take — mọi thứ xảy ra liên tục không cắt, hỗn loạn có kiểm soát",
}

# Combos that don't work with single continuous take Veo generation
_EXCLUDED_COMBOS = {
    ("reverse", "handheld_doc"),  # reverse timeline needs cuts, conflicts with doc feel
}

CINEMATIC_STYLES = {
    "commercial": "Clean, bright, aspirational — standard product ad look",
    "neon_noir": "Neon rim lights, dark backgrounds, dramatic shadows — Wong Kar-wai vibes",
    "golden_hour": "Warm golden backlighting, lens flares, dreamy — romantic film look",
    "wes_anderson": "Symmetrical framing, pastel colors, flat perspective — quirky and aesthetic",
    "handheld_doc": "Handheld camera, natural light, intimate — documentary/vlog feel",
}


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def generate_screenplay(
    product_title: str,
    product_description: str,
    kol_ids: list[str],
    story_style: str = "auto",
    cinematic_style: str = "auto",
    product_images: list[str] = None,
) -> dict:
    """Generate a 2-clip screenplay with shot-level breakdowns.
    Sends product images to Gemini so it can write visually specific scenes."""
    kol_descriptions = []
    for kid in kol_ids:
        profile = kol_manager.get_profile(kid)
        if profile:
            kol_descriptions.append(f"{profile['name']}: {profile.get('description', '')}")

    import random

    if story_style == "auto" or story_style not in STORY_STYLES:
        story_style = random.choice(list(STORY_STYLES.keys()))

    if cinematic_style == "auto" or cinematic_style not in CINEMATIC_STYLES:
        cinematic_style = random.choice(list(CINEMATIC_STYLES.keys()))

    # Re-roll if combo is excluded (max 5 attempts)
    for _ in range(5):
        if (story_style, cinematic_style) not in _EXCLUDED_COMBOS:
            break
        cinematic_style = random.choice(list(CINEMATIC_STYLES.keys()))

    style_desc = STORY_STYLES[story_style]
    cinema_desc = CINEMATIC_STYLES[cinematic_style]

    prompt_template = _load_prompt()
    prompt_text = prompt_template.format(
        product_title=product_title,
        product_description=product_description,
        kol_descriptions="\n".join(kol_descriptions) if kol_descriptions else "Nhân vật chính (nữ trẻ)",
        story_style=f"{story_style} — {style_desc}",
        cinematic_style=f"{cinematic_style} — {cinema_desc}",
    )

    # Build multimodal contents: product images + prompt text
    contents = []
    loaded_count = 0
    if product_images:
        for img_url in product_images[:3]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                try:
                    contents.append(_resize_for_input(Image.open(local)))
                    loaded_count += 1
                except Exception as e:
                    log.warning(f"Failed to load product image {local}: {e}")
            else:
                log.warning(f"Product image not found: {local} (from url: {img_url})")
        if loaded_count:
            contents.append(
                "PRODUCT PHOTOS above — use these to write visually accurate scenes:\n"
                "- Note the product's color, shape, size, packaging, texture\n"
                "- Incorporate these SPECIFIC visual details into key_frame_description and action\n"
                "- The product in your screenplay must look like THESE photos"
            )
    contents.append(prompt_text)

    log.info(f"Generating screenplay with {loaded_count}/{len(product_images or [])} product images loaded")

    # Call Gemini with retry
    client = _get_client()
    last_err = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            break
        except Exception as e:
            last_err = e
            if "503" in str(e) or "429" in str(e) or "overloaded" in str(e).lower():
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Gemini API error: {e}") from e
    else:
        raise RuntimeError(f"Gemini API error after 3 retries: {last_err}") from last_err

    # Check for truncation
    finish_reason = None
    if resp.candidates:
        finish_reason = getattr(resp.candidates[0], 'finish_reason', None)
    log.info(f"Screenplay response: {len(resp.text)} chars, finish_reason={finish_reason}")

    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    import re
    result = None
    for t in [
        text,
        re.sub(r',\s*([}\]])', r'\1', text),
        re.sub(r',\s*([}\]])', r'\1', text.replace('\n', '\\n')),
        re.sub(r',\s*([}\]])', r'\1', re.sub(r"(?<=[{,\[])\s*'([^']+)'\s*:", r' "\1":', re.sub(r":\s*'([^']*)'", r': "\1"', text))),
    ]:
        try:
            result = json.loads(t)
            break
        except json.JSONDecodeError:
            continue

    # Last resort: truncated JSON — try closing brackets
    if result is None:
        for suffix in ['"}]}]}', '"]}]}', ']}]}', '"}]}', '"]}', ']}', '}}', '}']:
            try:
                result = json.loads(text + suffix)
                log.info("Screenplay JSON repaired by closing brackets")
                break
            except (json.JSONDecodeError, TypeError):
                continue

    if result is None:
        log.warning(f"Screenplay JSON parse failed. finish_reason={finish_reason}. "
                    f"Raw text ({len(text)} chars): {text[:800]}")
        raise RuntimeError(f"Kịch bản bị lỗi JSON. Thử lại (Gemini sẽ tạo lại).")

    if isinstance(result, list):
        result = result[0] if result else {}

    # Compatibility: old clips[] format → convert to segments[]
    if "clips" in result and isinstance(result["clips"], list) and len(result["clips"]) > 0:
        clips = result["clips"]
        segments = []
        for clip in clips:
            segments.append({
                "type": "story",
                "duration": 8,
                "prompt": clip.get("motion_prompt", ""),
                "dialogue": clip.get("dialogue"),
            })
        result["segments"] = segments
        if not result.get("key_frame_description"):
            result["key_frame_description"] = clips[0].get("key_frame_description", "")
        del result["clips"]

    # Compatibility: old flat motion_prompt → convert to segments[]
    if "segments" not in result and result.get("motion_prompt"):
        segments = [{"type": "story", "duration": 8, "prompt": result["motion_prompt"]}]
        result["segments"] = segments

    # Validate segments: single 8s segment
    segments = result.get("segments", [])
    if segments:
        segments = segments[:1]
        segments[0]["duration"] = 8
        segments[0].setdefault("type", "story")
        segments[0].setdefault("prompt", "")
        result["segments"] = segments

    result.setdefault("title", product_title)
    result.setdefault("story_hook", "")
    result.setdefault("product_placement", "")
    result.setdefault("key_frame_description", "")
    result.setdefault("mood", "")
    result.setdefault("segments", [{"type": "story", "duration": 8, "prompt": ""}])
    result.setdefault("dialogue", None)
    result.setdefault("marketing_overlay", {
        "hook_overlay": "",
        "benefit_overlay": "",
        "cta_overlay": "Link mua ở mô tả nhé!",
    })
    result.setdefault("cinematic_style", cinematic_style)
    result["kol_ids"] = kol_ids
    result["story_style"] = story_style

    # Remove legacy flat fields if present (segments is the source of truth now)
    result.pop("motion_prompt", None)
    result.pop("extend_prompt", None)
    result.pop("shots", None)

    return result


def get_story_styles() -> dict:
    return STORY_STYLES


def get_cinematic_styles() -> dict:
    return CINEMATIC_STYLES


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        data = yaml.safe_load(PROMPT_PATH.read_text())
        return data.get("template", "")
    return _DEFAULT_TEMPLATE


_DEFAULT_TEMPLATE = """(Fallback — see prompts/movie_screenplay.yaml for full prompt)
Viết kịch bản 16s cho sản phẩm: {product_title}
Mô tả: {product_description}
Nhân vật: {kol_descriptions}
Phong cách: {story_style} / {cinematic_style}

Output JSON with: title, story_hook, product_placement, mood, marketing_overlay, key_frame_description, segments[], dialogue.
segments is array of objects with type (story/closeup), duration (4/6/8), prompt (English for Veo). Total duration must = 16."""
