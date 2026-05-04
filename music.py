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


GENRE_KEYWORDS = {
    "happy": ["trẻ em", "bé", "mầm non", "thiếu nhi", "đồ chơi"],
    "acoustic": ["sách", "book", "học", "giáo dục"],
    "lofi": ["thời trang", "áo", "quần", "váy", "giày"],
    "corporate": ["công nghệ", "laptop", "điện thoại", "tai nghe"],
    "piano": ["mỹ phẩm", "skincare", "serum", "kem"],
}


def get_background_music(product_title: str = "") -> str | None:
    """Pick genre by product keywords, fetch/cache from Freesound. Returns local path or None."""
    from pathlib import Path
    music_dir = Path(__file__).parent / "music"
    music_dir.mkdir(exist_ok=True)

    genre = "lofi"
    if product_title:
        t = product_title.lower()
        for g, keywords in GENRE_KEYWORDS.items():
            if any(w in t for w in keywords):
                genre = g
                break

    cached = list(music_dir.glob(f"{genre}_*.mp3"))
    if cached:
        return str(random.choice(cached))

    api_key = os.getenv("FREESOUND_API_KEY", "")
    if not api_key:
        return None
    try:
        r = httpx.get("https://freesound.org/apiv2/search/text/", params={
            "token": api_key, "query": f"{genre} background",
            "filter": "duration:[15 TO 60]",
            "fields": "id,name,previews", "page_size": "5", "sort": "rating_desc",
        }, timeout=10)
        results = r.json().get("results", [])
        if results:
            url = random.choice(results).get("previews", {}).get("preview-hq-mp3", "")
            if url:
                audio = httpx.get(url, timeout=15, follow_redirects=True)
                if audio.status_code == 200:
                    cached_path = music_dir / f"{genre}_{random.randint(1000,9999)}.mp3"
                    cached_path.write_bytes(audio.content)
                    return str(cached_path)
    except Exception:
        pass
    return None
