"""Search free music from Freesound or Jamendo."""

import os
import random

import httpx

CATEGORIES = ["happy", "sad", "calm", "energetic", "acoustic", "piano", "lofi", "jazz", "pop", "cinematic", "corporate", "ambient"]


async def search_music(category: str = "", q: str = "", refresh: bool = False, source: str = "freesound") -> dict:
    search = q or category or "background music"
    if source == "jamendo":
        return await _search_jamendo(search, refresh)
    return await _search_freesound(search, refresh)


async def _search_freesound(search: str, refresh: bool) -> dict:
    api_key = os.getenv("FREESOUND_API_KEY", "")
    if not api_key:
        return {"tracks": [], "categories": CATEGORIES, "error": "Cần FREESOUND_API_KEY"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://freesound.org/apiv2/search/text/", params={
                "token": api_key,
                "query": search,
                "filter": "duration:[15 TO 120]",
                "fields": "id,name,duration,previews,tags",
                "page_size": "20",
                "sort": "rating_desc" if not refresh else "score",
            })
            data = resp.json()
            tracks = []
            for r in data.get("results", []):
                url = r.get("previews", {}).get("preview-hq-mp3", "")
                if url:
                    tags = r.get("tags", [])[:3]
                    tracks.append({"name": r["name"], "url": url, "duration": round(r.get("duration", 0)), "category": tags[0] if tags else ""})
            if refresh:
                random.shuffle(tracks)
            return {"tracks": tracks, "categories": CATEGORIES, "source": "freesound"}
    except Exception as e:
        return {"tracks": [], "categories": CATEGORIES, "error": str(e)[:100]}


async def _search_jamendo(search: str, refresh: bool) -> dict:
    client_id = os.getenv("JAMENDO_CLIENT_ID", "")
    if not client_id:
        return {"tracks": [], "categories": CATEGORIES, "error": "Cần JAMENDO_CLIENT_ID"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.jamendo.com/v3.0/tracks/", params={
                "client_id": client_id,
                "format": "json",
                "limit": "20",
                "search": search,
                "audioformat": "mp32",
                "order": "popularity_total" if not refresh else "relevance",
                "duration_between": "15_120",
            })
            data = resp.json()
            tracks = []
            for r in data.get("results", []):
                url = r.get("audio", "")
                if url:
                    tracks.append({"name": r["name"], "url": url, "duration": r.get("duration", 0), "category": r.get("genre", "")})
            if refresh:
                random.shuffle(tracks)
            return {"tracks": tracks, "categories": CATEGORIES, "source": "jamendo"}
    except Exception as e:
        return {"tracks": [], "categories": CATEGORIES, "error": str(e)[:100]}
