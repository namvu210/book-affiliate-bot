"""Scene image generation for Movie Ads — multi-reference composition via Gemini Image."""

import asyncio
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY, log, output_path, output_url
from imagegen import _resize_for_input, EDIT_MODEL
import kol_manager


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


async def generate_scene_image(
    project_id: str,
    clip_number: int,
    key_frame_description: str,
    kol_ids: list[str],
    product_images: list[str] = None,
    cinematic_style: str = "",
    prev_clip_image: str | None = None,
    prev_clip_description: str = "",
) -> str | None:
    """Generate a scene key frame image using KOL references + product images + description.

    Args:
        prev_clip_image: Path/URL of previous clip's scene image for visual continuity.
        prev_clip_description: Description of previous clip's last moment for context.

    Returns the output URL of the generated image, or None on failure.
    """
    contents = []

    # 1. KOL reference images FIRST (critical for identity preservation)
    kol_ref_count = 0
    for kol_id in kol_ids:
        ref_paths = kol_manager.get_reference_paths(kol_id)
        profile = kol_manager.get_profile(kol_id)
        for ref_path in ref_paths:
            try:
                img = _resize_for_input(Image.open(ref_path))
                contents.append(img)
                kol_ref_count += 1
            except Exception:
                pass
        if profile and ref_paths:
            contents.append(
                f"CHARACTER REFERENCE — '{profile['name']}': {profile.get('description', '')}\n"
                f"- COPY EXACTLY: face shape, skin tone, hair style/color, body proportions, age\n"
                f"- IGNORE: clothing, background, pose, lighting from reference photos\n"
                f"- Dress and pose the character according to the SCENE DESCRIPTION below"
            )

    # 2. Previous clip image for continuity (clip 2+)
    if prev_clip_image:
        local = str(Path(".") / prev_clip_image.lstrip("/"))
        if Path(local).exists():
            try:
                contents.append(_resize_for_input(Image.open(local)))
                contents.append(
                    f"PREVIOUS CLIP'S KEY FRAME (above) — this is the END of clip {clip_number - 1}.\n"
                    f"{f'Previous clip ended with: {prev_clip_description}' if prev_clip_description else ''}\n"
                    f"CONTINUITY REQUIREMENTS:\n"
                    f"- SAME character appearance: identical clothing, hair, accessories, makeup\n"
                    f"- SAME environment/location unless the script explicitly changes it\n"
                    f"- CONSISTENT color palette and lighting temperature\n"
                    f"- This new frame should feel like the NEXT MOMENT in the same story\n"
                    f"- Maintain spatial continuity (if character was on the left, don't flip)"
                )
            except Exception:
                pass

    # 3. Product images
    if product_images:
        for img_url in product_images[:2]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                try:
                    contents.append(_resize_for_input(Image.open(local)))
                except Exception:
                    pass
        if product_images:
            contents.append(
                "PRODUCT PHOTOS above — CRITICAL:\n"
                "- The product MUST be clearly VISIBLE and recognizable in this frame\n"
                "- Match the product's exact color, texture, shape, and details\n"
                "- The character should be WEARING or HOLDING the product\n"
                "- Product must be visible in EVERY clip (not just the final reveal)"
            )

    # 4. Scene description prompt
    contents.append(
        f"Generate a CINEMATIC STILL FRAME for a short film advertisement.\n\n"
        f"SCENE DESCRIPTION:\n{key_frame_description}\n\n"
        f"{'CINEMATIC STYLE: ' + cinematic_style + chr(10) + chr(10) if cinematic_style else ''}"
        f"REQUIREMENTS:\n"
        f"- This is a KEY FRAME (first frame of a video clip) — it must have CINEMATIC COMPOSITION\n"
        f"- Aspect ratio: 9:16 (vertical, phone-first)\n"
        f"- The character must match the REFERENCE PHOTOS exactly (face, hair, body)\n"
        f"- Lighting, color grade, and mood must match the scene description\n"
        f"- Frame it like a real film frame — shallow depth of field, intentional focus\n"
        f"- NO stock photo aesthetic — this should look like a still from a Vietnamese indie film\n"
        f"- Any text/signs must be correct Vietnamese or English\n"
        f"- Capture a MOMENT IN MOTION — character mid-action, not static posing\n"
        f"- Strong visual storytelling: viewer should feel something from this single frame"
    )

    log.info(f"Generating scene image for project {project_id} clip {clip_number} "
             f"({kol_ref_count} KOL refs, {len(product_images or [])} product imgs)")

    try:
        client = _get_client()
        result = await asyncio.to_thread(
            client.models.generate_content,
            model=EDIT_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(aspect_ratio="9:16"),
            ),
        )

        for part in (result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []):
            if part.inline_data:
                img_dir = output_path(project_id, "scene_images")
                img_dir.mkdir(parents=True, exist_ok=True)
                img_path = img_dir / f"clip_{clip_number}.png"
                img_path.write_bytes(part.inline_data.data)
                url = f"{output_url(project_id, 'scene_images')}/clip_{clip_number}.png"
                log.info(f"Scene image generated: {url} ({len(part.inline_data.data)} bytes)")
                return url

        # Log failure details
        parts = result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []
        text_parts = [p.text for p in parts if hasattr(p, 'text') and p.text]
        finish = getattr(result.candidates[0], 'finish_reason', 'unknown') if result.candidates else 'no candidates'
        log.warning(f"Scene image clip {clip_number}: no image returned. Finish: {finish}. Text: {'; '.join(text_parts)[:200]}")

    except Exception as e:
        log.warning(f"Scene image generation failed for clip {clip_number}: {type(e).__name__}: {e}")

    return None
