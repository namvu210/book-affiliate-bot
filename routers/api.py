"""Miscellaneous API routes — models, music, voices."""

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/elevenlabs-voices")
async def elevenlabs_voices():
    """List available ElevenLabs voices."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"voices": [], "error": "Cần ELEVENLABS_API_KEY trong .env"}
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        resp = client.voices.get_all()
        voices = [{"id": v.voice_id, "name": v.name, "category": v.category or ""} for v in resp.voices]
        order = {"cloned": 0, "generated": 1, "professional": 2, "premade": 3}
        voices.sort(key=lambda v: (order.get(v["category"], 9), v["name"]))
        return {"voices": voices[:10]}
    except Exception as e:
        return {"voices": [], "error": str(e)[:200]}


@router.get("/set-model")
async def set_model(model: str = "gemini-2.5-flash-lite"):
    """Switch Gemini model at runtime."""
    import reviewer
    try:
        reviewer.set_model(model)
        return {"status": "ok", "model": model}
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/set-image-model")
async def set_image_model(model: str = "gemini-2.5-flash-image"):
    """Switch image generation model at runtime."""
    from imagegen import set_image_model as _set
    _set(model)
    return {"status": "ok", "model": model}


@router.get("/models")
async def list_models():
    """List available Gemini models."""
    from google import genai
    from config import GEMINI_API_KEY, GEMINI_MODEL
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = []
        for m in client.models.list():
            models.append(m.name.replace("models/", ""))
        models = [m for m in models if m.startswith("gemini")]
        return {"models": sorted(models, reverse=True), "current": GEMINI_MODEL}
    except Exception:
        return {"models": [
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
        ]}


@router.get("/music")
async def get_music(category: str = "", q: str = "", refresh: bool = False, source: str = "freesound"):
    """Search free music from Freesound or Jamendo."""
    from music import search_music
    return await search_music(category, q, refresh, source)
