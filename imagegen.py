"""AI lifestyle image generation using Gemini image editing."""

import json
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY, log, output_path, output_url

EDIT_MODEL = "gemini-2.5-flash-image"
SCENE_MODEL = "gemini-2.5-flash-lite"

# Max dimension for input images sent to Gemini (reduces token cost ~75%)
INPUT_MAX_PX = 512


def _resize_for_input(img: Image.Image) -> Image.Image:
    """Resize image to fit within INPUT_MAX_PX box to reduce Gemini token cost."""
    if max(img.size) > INPUT_MAX_PX:
        img = img.copy()
        img.thumbnail((INPUT_MAX_PX, INPUT_MAX_PX))
    return img


def set_image_model(name: str):
    """Switch the image generation model at runtime."""
    global EDIT_MODEL
    EDIT_MODEL = name
KOL_DIR = Path(__file__).parent / "kol"
MAX_AI_IMAGES = 4


def save_kol_photo(data: bytes, filename: str, slot: int = 1) -> str:
    """Save KOL reference photo (slot 1 = front, slot 2 = side angle)."""
    KOL_DIR.mkdir(exist_ok=True)
    ext = Path(filename).suffix.lower() or ".jpg"
    path = KOL_DIR / f"kol_reference_{slot}{ext}"
    path.write_bytes(data)
    # Keep backward compat: slot 1 also saves as kol_reference for old code
    if slot == 1:
        compat = KOL_DIR / f"kol_reference{ext}"
        compat.write_bytes(data)
    return str(path)


def get_kol_photos() -> list[str]:
    """Get all saved KOL reference photo paths (up to 2)."""
    KOL_DIR.mkdir(exist_ok=True)
    photos = []
    for slot in [1, 2]:
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            p = KOL_DIR / f"kol_reference_{slot}{ext}"
            if p.exists():
                photos.append(str(p))
                break
    # Fallback: old single-file format
    if not photos:
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            p = KOL_DIR / f"kol_reference{ext}"
            if p.exists():
                return [str(p)]
    return photos


def get_kol_photo() -> str | None:
    """Get primary KOL reference photo path (backward compat)."""
    photos = get_kol_photos()
    return photos[0] if photos else None



def generate_scene_descriptions(product_title: str, persona: dict, num_scenes: int, product_images: list[str] = None) -> tuple[str, list[str], bool, str]:
    """Use multimodal LLM to generate product description + scene descriptions.
    Returns (product_description, [scene1, ...], same_person, end_user)."""
    if num_scenes <= 0:
        return "", [], True, ""
    persona_name = persona.get("name", "Khách hàng") if isinstance(persona, dict) else str(persona)
    persona_focus = persona.get("focus", "") if isinstance(persona, dict) else ""

    prompt = (
        f"You are a professional TikTok product photographer in Vietnam, known for creative angles and scroll-stopping compositions.\n\n"
        f"Product: {product_title}\n"
        f"Target customer: {persona_name} ({persona_focus})\n\n"
        f"Generate {num_scenes} SHORT photo direction instructions for AI image generation.\n\n"
        f"CRITICAL — WHO APPEARS IN THE PHOTO:\n"
        f"The buyer ('{persona_name}') is NOT always the person who uses the product.\n"
        f"- Children's books/toys/clothes → show a CHILD using it, NOT the parent\n"
        f"- Pet products → show the PET, NOT the owner\n"
        f"- Gift items → show the RECIPIENT, NOT the buyer\n"
        f"- Adult products → show the buyer using it\n\n"
        f"CAMERA ANGLES — each scene MUST use a DIFFERENT angle from this list:\n"
        f"- Overhead flat lay (top-down, product arranged on surface)\n"
        f"- Dutch angle (tilted 15-30°, dynamic energy)\n"
        f"- Low angle looking up (product/person appears powerful)\n"
        f"- Over-the-shoulder POV (viewer sees what the person sees)\n"
        f"- Extreme close-up (texture, material detail, macro)\n"
        f"- Wide establishing shot (person small in environment)\n"
        f"- Waist-up portrait with product (classic influencer)\n"
        f"- Hands-only shot (hands interacting with product, no face)\n"
        f"- Reflection/mirror shot (creative framing)\n"
        f"- Motion blur / action shot (person using product dynamically)\n\n"
        f"SETTING — match the product naturally:\n"
        f"  * Underwear/lingerie → bedroom, flat lay on bed. NEVER in public.\n"
        f"  * Swimwear → beach, pool\n"
        f"  * Sleepwear → bedroom, living room\n"
        f"  * Fashion → café, street, park\n"
        f"  * Kitchen items → kitchen\n"
        f"  * Books/stationery → desk, café, library\n\n"
        f"MANDATORY SEQUENCE:\n"
        f"- Image 1: Product extreme close-up/detail (texture, label, material). No person.\n"
        f"- Image 2+: Each uses a DIFFERENT camera angle. NO two scenes with the same angle.\n\n"
        f"Each instruction: camera angle + person interaction + setting + lighting. Under 80 words.\n"
        f"Return JSON: {{\"product_description\": \"product appearance from photos\", \"same_person\": true/false (does the buyer USE this product themselves? true=buyer wears/uses it, false=child/pet/recipient uses it), \"end_user\": \"who actually uses the product\", \"scenes\": [\"scene1\", ...]}}"
    )

    contents = []
    if product_images:
        for img_path in product_images[:2]:
            local = str(Path(".") / img_path.lstrip("/"))
            if Path(local).exists():
                try:
                    contents.append(_resize_for_input(Image.open(local)))
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
            same_person = result.get("same_person", True)
            end_user = result.get("end_user", persona_name)
            log.info(f"Product desc: {desc[:80]}... | same_person={same_person}, end_user={end_user}")
            return desc, scenes, same_person, end_user
        elif isinstance(result, list):
            return "", [s for s in result if isinstance(s, str)][:num_scenes], True, persona_name
    except Exception as e:
        log.warning(f"Scene description failed: {e}")
    return "", [], True, persona_name


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
            img = _resize_for_input(Image.open(local))
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

    # Combined: scene descriptions + end-user detection in one LLM call
    product_desc, scenes, use_kol, end_user_desc = generate_scene_descriptions(product_title, persona, num, product_images)
    if not end_user_desc:
        end_user_desc = persona_name
    log.info(f"Roles: same_person={use_kol}, end_user={end_user_desc}")
    if not scenes:
        return []

    # Load reference images
    kol_imgs = []
    if use_kol:
        for kol_path in get_kol_photos():
            try:
                kol_imgs.append(_resize_for_input(Image.open(kol_path)))
                log.info(f"KOL photo loaded: {kol_path}")
            except Exception:
                pass
    if not kol_imgs:
        log.info(f"KOL not used (use_kol={use_kol}, photos={len(get_kol_photos())})")

    if not product_desc and not scenes:
        log.warning(f"No product description or scenes generated")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)

    img_dir = output_path(ts, "ai_images")
    img_dir.mkdir(parents=True, exist_ok=True)

    # Load product images once (shared across all parallel calls)
    prod_imgs = []
    if product_images:
        for img_url in product_images[:2]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                try:
                    prod_imgs.append(_resize_for_input(Image.open(local)))
                except Exception:
                    pass

    import asyncio

    async def _gen_one(i, scene):
        """Generate a single lifestyle image."""
        try:
            contents = []
            for pimg in prod_imgs:
                contents.append(pimg)
            if prod_imgs:
                contents.append("PRODUCT PHOTOS above: match the product appearance exactly.")
            if product_desc:
                contents.append(f"Product appearance: {product_desc}")
            if kol_imgs:
                for kimg in kol_imgs:
                    contents.append(kimg)
                angle_note = " (front + side angle)" if len(kol_imgs) >= 2 else ""
                contents.append(
                    f"PERSON REFERENCE{angle_note} — FACE AND BODY ONLY:\n"
                    "- COPY: face shape, skin tone, hair style, body type, approximate age\n"
                    "- NEVER COPY: clothing, accessories, background, pose, lighting from these photos\n"
                    "- The person must wear the PRODUCT or clothing appropriate to the scene\n"
                    "- The background must match the SCENE DESCRIPTION, NOT the reference photo background"
                )

            if use_kol and kol_imgs:
                person_instruction = (
                    "The person MUST match the PERSON REFERENCE face/body. "
                    "IGNORE their outfit and background — dress them in the product or scene-appropriate clothing."
                )
            else:
                person_instruction = f"Show a {end_user_desc} (Vietnamese) with the product in a natural way."

            is_first = (i == 0)
            first_image_rule = (
                "FIRST IMAGE HOOK: This is the video thumbnail — it must STOP THE SCROLL. "
                "Use the most dramatic angle, strongest contrast, or intriguing partial reveal. "
                "Bold color or unexpected composition that breaks pattern in a feed."
            ) if is_first else ""

            contents.append(
                f"Create a new lifestyle photo: {scene}\n\n"
                f"{person_instruction}\n\n"
                f"The product must look exactly like the reference photos.\n\n"
                f"{first_image_rule}\n\n"
                f"COLOR & CONTRAST:\n"
                f"- ONE bold accent color contrasting with background\n"
                f"- Dramatic light/shadow (60/40 ratio minimum)\n"
                f"- Product is the brightest/most saturated element\n"
                f"- Background slightly desaturated to make product pop\n\n"
                f"COMPOSITION:\n"
                f"- Subject fills at least 60% of frame\n"
                f"- Asymmetric framing (rule of thirds, NOT dead center)\n"
                f"- Leading lines or gaze direction pointing toward product\n\n"
                f"EMOTION:\n"
                f"- Capture a MOMENT, not a pose (mid-action, not static)\n"
                f"- Include one sensory detail (texture catching light, fabric draping, pages mid-flip)\n\n"
                f"TIKTOK STYLE:\n"
                f"- Warm color temperature, shallow depth of field\n"
                f"- Natural imperfection (lived-in, real-life feel)\n"
                f"- NO stock photo aesthetic, no white void, no corporate lighting\n"
                f"- Think 'iPhone photo by a stylish friend'\n\n"
                f"RULES:\n"
                f"- Vietnamese setting matching the scene description\n"
                f"- Any text/signs MUST be correct Vietnamese or English — no gibberish\n"
                f"- Brand names must match real product photos exactly"
            )

            log.info(f"Editing image {i+1}/{len(scenes)}...")
            result = await asyncio.to_thread(
                client.models.generate_content,
                model=EDIT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )

            for part in (result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []):
                if part.inline_data:
                    img_path = img_dir / f"ai_{i}.png"
                    img_path.write_bytes(part.inline_data.data)
                    log.info(f"Generated image {i+1}/{len(scenes)} ({len(part.inline_data.data)} bytes)")
                    return f"{output_url(ts, 'ai_images')}/ai_{i}.png"
            else:
                parts = result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []
                text_parts = [p.text for p in parts if hasattr(p, 'text') and p.text]
                finish = getattr(result.candidates[0], 'finish_reason', 'unknown') if result.candidates else 'no candidates'
                log.warning(f"Image {i+1}: no image returned. Finish: {finish}. Text: {'; '.join(text_parts)[:200]}")
                if 'IMAGE_OTHER' in str(finish) or 'SAFETY' in str(finish):
                    try:
                        retry_contents = []
                        if product_desc:
                            retry_contents.append(f"Product: {product_desc}")
                        retry_contents.append(
                            f"Create a product photography flat-lay image: the product laid out on a clean surface "
                            f"with soft lighting. Vietnamese aesthetic. No people, no models. "
                            f"High quality product photography for social media."
                        )
                        retry_result = await asyncio.to_thread(
                            client.models.generate_content,
                            model=EDIT_MODEL, contents=retry_contents,
                            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                        )
                        for rp in (retry_result.candidates[0].content.parts if retry_result.candidates and retry_result.candidates[0].content else []):
                            if rp.inline_data:
                                img_path = img_dir / f"ai_{i}.png"
                                img_path.write_bytes(rp.inline_data.data)
                                log.info(f"Retry image {i+1}: flat-lay generated ({len(rp.inline_data.data)} bytes)")
                                return f"{output_url(ts, 'ai_images')}/ai_{i}.png"
                    except Exception as re:
                        log.warning(f"Retry image {i+1} also failed: {re}")
        except Exception as e:
            log.warning(f"Image {i+1} failed: {type(e).__name__}: {e}")
        return None

    results = await asyncio.gather(*[_gen_one(i, scene) for i, scene in enumerate(scenes)])
    paths = [r for r in results if r]
    return paths
