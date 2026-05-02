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
MAX_AI_IMAGES = 3


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
        f"- Vietnamese setting APPROPRIATE for the product:\n"
        f"  * Underwear/lingerie/bras → bedroom, dressing room, flat lay on bed. NEVER in public.\n"
        f"  * Swimwear → beach, pool area\n"
        f"  * Sleepwear/pajamas → bedroom, living room at home\n"
        f"  * Outerwear/fashion → café, street, office, park\n"
        f"  * Kitchen items → kitchen\n"
        f"  * Books/stationery → desk, café, library\n"
        f"  * Choose the most NATURAL setting where this product would actually be used/worn\n"
        f"- Camera angle (close-up, waist-up, full body)\n"
        f"- Lighting and mood\n\n"
        f"MANDATORY: The FIRST image must be a product close-up/detail shot — "
        f"focus on the product itself (texture, material, label, design details). "
        f"No full body, no person — just the product up close. "
        f"The remaining images show the person with the product.\n\n"
        f"Keep each instruction under 100 words.\n"
        f"Return JSON array of strings only."
    )

    contents = []
    kol_path = get_kol_photo()
    if kol_path:
        try:
            contents.append(Image.open(kol_path))
            contents.append("Above: KOL/reviewer reference photo. Describe this person's appearance "
                          "(body shape, skin tone, hair style, approximate age) and reference it in your scene descriptions.")
        except Exception:
            pass
    if product_images:
        for img_path in product_images[:2]:
            local = str(Path(".") / img_path.lstrip("/"))
            if Path(local).exists():
                try:
                    contents.append(Image.open(local))
                except Exception:
                    pass
        contents.append("Above: Real product photos. Use these ONLY for the product appearance "
                      "(color, shape, material, brand). IGNORE any people/models shown in these photos — "
                      "use the KOL reference photo for the person's appearance instead.")
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


def _detect_end_user(product_title: str, persona_name: str) -> dict:
    """Determine if buyer = end_user. Returns {"same_person": bool, "end_user": str}."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=SCENE_MODEL,
            contents=(
                f"Product: {product_title}\nBuyer: {persona_name}\n\n"
                f"Is the buyer the same person who USES this product?\n"
                f"Examples: adult buys shirt for themselves → same. Parent buys toy for child → different.\n"
                f"Return JSON: {{\"same_person\": true/false, \"end_user\": \"description of who uses it\"}}"
            ),
            config=types.GenerateContentConfig(max_output_tokens=100, response_mime_type="application/json"),
        )
        import json
        return json.loads(resp.text.strip())
    except Exception as e:
        print(f"[imagegen] Role detection failed: {e}")
        return {"same_person": True, "end_user": persona_name}


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

    persona_name = persona.get("name", "Khách hàng") if isinstance(persona, dict) else str(persona)

    # Detect roles: should we use KOL photo or describe end_user?
    roles = _detect_end_user(product_title, persona_name)
    use_kol = roles.get("same_person", True)
    end_user_desc = roles.get("end_user", persona_name)
    print(f"[imagegen] Roles: same_person={use_kol}, end_user={end_user_desc}")

    scenes = generate_scene_descriptions(product_title, persona, num, product_images)
    if not scenes:
        return []

    # Load reference images
    kol_path = get_kol_photo()
    kol_img = None
    if kol_path and use_kol:
        try:
            kol_img = Image.open(kol_path)
            print(f"[imagegen] KOL photo loaded: {kol_path}")
        except Exception:
            print(f"[imagegen] KOL photo failed to load")
    else:
        print(f"[imagegen] KOL not used (use_kol={use_kol}, kol_path={'set' if kol_path else 'none'})")

    product_imgs = []
    if product_images:
        for img_url in product_images[:4]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                try:
                    product_imgs.append(Image.open(local))
                except Exception:
                    pass
        print(f"[imagegen] Loaded {len(product_imgs)} product images")
    if not product_imgs:
        print(f"[imagegen] No product images. URLs: {product_images[:2] if product_images else '[]'}")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)
    img_dir = output_path(ts, "ai_images")
    img_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, scene in enumerate(scenes):
        try:
            # Build edit request
            contents = []
            if kol_img:
                contents.append(kol_img)
                contents.append("Above: KOL reference photo. IMPORTANT: Keep this person's exact body shape, "
                              "skin tone, hair style, and proportions. The person in the output must look like "
                              "the same person in this reference photo. Only change their clothing and setting.")
            for pi, pimg in enumerate(product_imgs):
                contents.append(pimg)
            contents.append(f"Above: {len(product_imgs)} real product photos showing the SAME product from different angles. "
                          "Look at ALL photos to understand the product's exact appearance (color, shape, material, design). "
                          "IGNORE any people/models in these photos — use only the KOL reference for the person. "
                          "The product in your output must match what you see across ALL these reference photos.")
            if use_kol and kol_img:
                person_instruction = ("Use the KOL reference person with the product. "
                                     "The person MUST have the SAME body shape, skin tone, and hair as the KOL reference photo above. "
                                     "This is critical — do NOT use a different person.")
            else:
                person_instruction = f"Show a {end_user_desc} (Vietnamese) with the product in a natural way."
            contents.append(
                f"Create a new lifestyle photo: {scene} "
                f"{person_instruction} "
                f"The product must look exactly like the reference photos. "
                f"Vietnamese setting. High quality product photography for TikTok. "
                f"IMPORTANT: All details must be realistic and factual. "
                f"Any text, signs, labels, or writing in the image MUST be correct Vietnamese or English — "
                f"no gibberish, no fake characters, no misspelled words. "
                f"Brand names on the product must match the real product photos exactly. "
                f"Background details (shop signs, menus, posters) must use real, readable text."
            )

            print(f"[imagegen] Editing image {i+1}/{len(scenes)}...")
            result = client.models.generate_content(
                model=EDIT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )

            for part in (result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []):
                if part.inline_data:
                    img_path = img_dir / f"ai_{i}.png"
                    img_path.write_bytes(part.inline_data.data)
                    paths.append(f"{output_url(ts, 'ai_images')}/ai_{i}.png")
                    print(f"[imagegen] Generated image {i+1}/{len(scenes)} ({len(part.inline_data.data)} bytes)")
                    break
        except Exception as e:
            print(f"[imagegen] Image {i+1} failed: {type(e).__name__}: {e}")
    return paths
