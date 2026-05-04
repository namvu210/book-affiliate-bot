"""AI lifestyle image generation using Gemini image editing."""

import json
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY, log, output_path, output_url

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


def generate_scene_descriptions(product_title: str, persona: dict, num_scenes: int, product_images: list[str] = None) -> tuple[str, list[str]]:
    """Use multimodal LLM to generate product description + scene descriptions.
    Returns (product_description, [scene1, scene2, ...])."""
    if num_scenes <= 0:
        return "", []
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
        f"Return JSON object: {{\"product_description\": \"detailed description of the product appearance from the photos\", \"scenes\": [\"scene1\", \"scene2\", ...]}}"
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
        log.info(f"Generating {num_scenes} scene descriptions...")
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
        if isinstance(result, dict):
            desc = result.get("product_description", "")
            scenes = [s for s in result.get("scenes", []) if isinstance(s, str)][:num_scenes]
            log.info(f"Product desc: {desc[:80]}...")
            return desc, scenes
        elif isinstance(result, list):
            return "", [s for s in result if isinstance(s, str)][:num_scenes]
    except Exception as e:
        log.warning(f"Scene description failed: {e}")
    return "", []


def _detect_end_user(product_title: str, persona_name: str) -> dict:
    """Determine if buyer = end_user. Returns {"same_person": bool, "end_user": str}."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=SCENE_MODEL,
            contents=(
                f"Product: {product_title}\nBuyer: {persona_name}\n\n"
                f"Does the buyer USE this product themselves? Answer same_person=true if YES.\n\n"
                f"same_person=true examples:\n"
                f"- Woman buys women's clothing → true (she wears it)\n"
                f"- Man buys men's shoes → true\n"
                f"- Office worker buys laptop → true\n"
                f"- Woman buys skincare → true\n\n"
                f"same_person=false examples:\n"
                f"- Parent buys children's book → false (child reads it)\n"
                f"- Owner buys pet food → false (pet eats it)\n"
                f"- Person buys gift → false (recipient uses it)\n\n"
                f"Return JSON: {{\"same_person\": true/false, \"end_user\": \"who uses it\"}}"
            ),
            config=types.GenerateContentConfig(max_output_tokens=100, response_mime_type="application/json"),
        )
        import json
        return json.loads(resp.text.strip())
    except Exception as e:
        log.warning(f"Role detection failed: {e}")
        return {"same_person": True, "end_user": persona_name}


def filter_product_images(product_images: list[str], client) -> list[str]:
    """Filter out product photos containing human models. Returns paths without people."""
    clean = []
    for img_url in (product_images or [])[:6]:
        local = str(Path(".") / img_url.lstrip("/"))
        if not Path(local).exists():
            continue
        try:
            img = Image.open(local)
            resp = client.models.generate_content(
                model=SCENE_MODEL,
                contents=[img, "Does this image contain a person or human model? Answer ONLY 'yes' or 'no'."],
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            has_person = 'yes' in resp.text.strip().lower()
            if not has_person:
                clean.append(local)
                log.info(f"Product image {img_url[-30:]}: no person → included")
            else:
                log.info(f"Product image {img_url[-30:]}: has person → excluded")
        except Exception:
            pass
    return clean


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
    log.info(f"Roles: same_person={use_kol}, end_user={end_user_desc}")

    product_desc, scenes = generate_scene_descriptions(product_title, persona, num, product_images)
    if not scenes:
        return []

    # Load reference images
    kol_path = get_kol_photo()
    kol_img = None
    if kol_path and use_kol:
        try:
            kol_img = Image.open(kol_path)
            log.info(f"KOL photo loaded: {kol_path}")
        except Exception:
            log.warning(f"KOL photo failed to load")
    else:
        log.info(f"KOL not used (use_kol={use_kol}, kol_path={'set' if kol_path else 'none'})")

    if not product_desc and not scenes:
        log.warning(f"No product description or scenes generated")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)

    img_dir = output_path(ts, "ai_images")
    img_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, scene in enumerate(scenes):
        try:
            # Build edit request — product images (user-ordered: first images are product-only) + KOL
            contents = []

            # Send first 2 product images (user puts product-only images first)
            prod_count = 0
            if product_images:
                for img_url in product_images[:2]:
                    local = str(Path(".") / img_url.lstrip("/"))
                    if Path(local).exists():
                        try:
                            contents.append(Image.open(local))
                            prod_count += 1
                        except Exception:
                            pass
            if prod_count:
                contents.append("PRODUCT PHOTOS above: match the product appearance exactly.")

            # Product described via text (from scene description step)
            if product_desc:
                contents.append(f"Product appearance: {product_desc}")

            # KOL photo — the ONLY image reference for the person
            if kol_img:
                contents.append(kol_img)
                contents.append("PERSON REFERENCE (photo above): This is the person to show in the final image. "
                              "Match this person's face, body type, skin tone, and hair exactly.")

            if use_kol and kol_img:
                person_instruction = ("The person MUST look like the PERSON REFERENCE photo above. "
                                     "Dress this person in the product described in the PRODUCT DESCRIPTION text.")
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

            log.info(f"Editing image {i+1}/{len(scenes)}...")
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
                    log.info(f"Generated image {i+1}/{len(scenes)} ({len(part.inline_data.data)} bytes)")
                    break
        except Exception as e:
            log.warning(f"Image {i+1} failed: {type(e).__name__}: {e}")
    return paths
