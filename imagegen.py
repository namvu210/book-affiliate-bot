"""AI lifestyle image generation using Gemini image editing."""

import json
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY, output_path, output_url

EDIT_MODEL = "gemini-2.5-flash-image"
SCENE_MODEL = "gemini-2.5-flash-lite"
KOL_DIR = Path(__file__).parent / "kol"
MAX_AI_IMAGES = 2


def save_kol_photo(data: bytes, filename: str) -> str:
    """Save KOL reference photo."""
    KOL_DIR.mkdir(exist_ok=True)
    ext = Path(filename).suffix.lower() or ".jpg"
    path = KOL_DIR / f"kol_reference{ext}"
    path.write_bytes(data)
    return str(path)


def get_kol_photo() -> str | None:
    """Get saved KOL reference photo path."""
    KOL_DIR.mkdir(exist_ok=True)
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = KOL_DIR / f"kol_reference{ext}"
        if p.exists():
            return str(p)
    return None


def generate_scene_descriptions(product_title: str, persona: dict, num_scenes: int, product_images: list[str] = None) -> list[str]:
    """Use multimodal LLM to generate scene descriptions for image editing."""
    if num_scenes <= 0:
        return []
    persona_name = persona.get("name", "Khách hàng") if isinstance(persona, dict) else str(persona)
    persona_focus = persona.get("focus", "") if isinstance(persona, dict) else ""

    prompt = (
        f"You are a professional TikTok product photographer in Vietnam.\n\n"
        f"Product: {product_title}\n"
        f"Target customer: {persona_name} ({persona_focus})\n\n"
        f"I will use AI image editing to composite the KOL photo + product photo into lifestyle scenes.\n"
        f"Generate {num_scenes} SHORT editing instructions. Each instruction tells the AI how to combine "
        f"the KOL and product into one scene.\n\n"
        f"CRITICAL — WHO APPEARS IN THE PHOTO:\n"
        f"The buyer ('{persona_name}') is NOT always the person who uses the product.\n"
        f"Determine the actual END-USER based on the product:\n"
        f"- Children's books/toys/clothes → show a CHILD using it, NOT the parent\n"
        f"- Pet products → show the PET, NOT the owner\n"
        f"- Gift items → show the RECIPIENT, NOT the buyer\n"
        f"- Adult products → show the buyer using it\n"
        f"For '{product_title}': who is the end-user? Show THAT person with the product.\n\n"
        f"Each instruction should specify:\n"
        f"- How the person interacts with the product (wearing, holding, using)\n"
        f"- Vietnamese setting (café, office, home, street)\n"
        f"- Camera angle (close-up, waist-up, full body from neck down)\n"
        f"- 'No face shown, crop above chin'\n"
        f"- Lighting and mood\n\n"
        f"Keep each instruction under 100 words.\n"
        f"Return JSON array of strings only."
    )

    contents = []
    if product_images:
        for img_path in product_images[:2]:
            local = str(Path(".") / img_path.lstrip("/"))
            if Path(local).exists():
                try:
                    contents.append(Image.open(local))
                except Exception:
                    pass
    contents.append(prompt)

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print(f"[imagegen] Generating {num_scenes} scene descriptions...")
        resp = client.models.generate_content(
            model=SCENE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                response_mime_type="application/json",
            ),
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        if isinstance(result, list):
            return [s for s in result if isinstance(s, str)][:num_scenes]
    except Exception as e:
        print(f"[imagegen] Scene description failed: {e}")
    return []


async def generate_lifestyle_images(
    product_title: str,
    persona: dict,
    num_images: int,
    ts: str,
    product_images: list[str] = None,
) -> list[str]:
    """Generate AI lifestyle images by compositing KOL + product photos."""
    num = min(num_images, MAX_AI_IMAGES)
    if num <= 0:
        return []

    scenes = generate_scene_descriptions(product_title, persona, num, product_images)
    if not scenes:
        return []

    # Load reference images
    kol_path = get_kol_photo()
    kol_img = None
    if kol_path:
        try:
            kol_img = Image.open(kol_path)
        except Exception:
            pass

    product_img = None
    if product_images:
        local = str(Path(".") / product_images[0].lstrip("/"))
        print(f"[imagegen] Product image: {local} exists={Path(local).exists()}")
        if Path(local).exists():
            try:
                product_img = Image.open(local)
            except Exception as e:
                print(f"[imagegen] Failed to open: {e}")
    if not product_img:
        print(f"[imagegen] No product image. URLs: {product_images[:2] if product_images else '[]'}")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)
    img_dir = output_path(ts, "ai_images")
    img_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, scene in enumerate(scenes):
        try:
            # Build edit request: KOL photo + product photo + instruction
            contents = []
            if kol_img:
                contents.append(kol_img)
                contents.append("Above: KOL/reviewer reference photo. Match this person's body type and skin tone. "
                              "Dress them appropriately for the scene context.")
            contents.append(product_img)
            contents.append("Above: The real product. Keep its appearance identical in the output.")
            contents.append(
                f"Create a new lifestyle photo combining the person and product: {scene} "
                f"The product must look exactly like the reference photo. "
                f"Vietnamese setting. High quality product photography for TikTok."
            )

            print(f"[imagegen] Editing image {i+1}/{len(scenes)}...")
            result = client.models.generate_content(
                model=EDIT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )

            for part in result.candidates[0].content.parts:
                if part.inline_data:
                    img_path = img_dir / f"ai_{i}.png"
                    img_path.write_bytes(part.inline_data.data)
                    paths.append(f"{output_url(ts, 'ai_images')}/ai_{i}.png")
                    print(f"[imagegen] Generated image {i+1}/{len(scenes)} ({len(part.inline_data.data)} bytes)")
                    break
        except Exception as e:
            print(f"[imagegen] Image {i+1} failed: {type(e).__name__}: {e}")
    return paths
