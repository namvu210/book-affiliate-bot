# Book Affiliate Bot — Project Context

## Overview

A FastAPI web app that automates product affiliate content creation for Vietnamese social media (Facebook, TikTok, YouTube). Given a Shopee product URL, it extracts info, generates AI review scripts, synthesizes voice narration, and renders short-form videos with subtitles and background music.

**Language:** Vietnamese (UI, content, prompts)
**Runtime:** Python 3.13, macOS dev environment

## Tech Stack

| Layer | Tech |
|-------|------|
| Web framework | FastAPI + Uvicorn (HTTPS via self-signed certs) |
| AI/LLM | Google Gemini 2.5 Flash Lite (reviews, personas) |
| TTS | ElevenLabs v3 (primary), gTTS (fallback) |
| Video | MoviePy 2.2 + ffmpeg |
| Image | Pillow, pilmoji (emoji support), Gemini image gen |
| PDF | PyMuPDF (fitz) |
| HTTP | httpx (async) |
| Excel | openpyxl |
| Frontend | Vanilla JS (Jinja2 templates, no framework) |
| Auth | OAuth2 for TikTok, YouTube, Facebook |

## File Structure

```
├── app.py              Main FastAPI app (29KB, routes + endpoints)
├── config.py           Settings, env vars, audience templates, helpers
├── pipeline.py         Orchestration: extract → review → TTS → images → video
├── extractor.py        Product info extraction (Shopee URLs, PDFs, AffiPad API)
├── reviewer.py         Gemini AI review generation (JSON output)
├── tts.py              Voice synthesis (ElevenLabs/gTTS, speed control)
├── imagegen.py         AI lifestyle image generation via Gemini
├── poster.py           Social media posting (FB Graph API, TikTok, YouTube)
├── affiliate.py        AffiPad conversion + Short.io/Bitly URL shortening
├── importer.py         Excel import (URL + affiliate columns)
├── music.py            Background music selection (keyword-based)
├── auth.py             OAuth flows (TikTok, YouTube, Facebook)
├── video/
│   ├── __init__.py     Package exports
│   ├── prepare.py      VideoInput dataclass + render_video orchestrator
│   ├── render.py       Core video rendering (MoviePy composition)
│   ├── effects.py      Image effects (ken_burns, zoom, pan)
│   ├── media.py        Media helpers (PDF cover extraction)
│   └── text.py         Text overlay rendering
├── templates/
│   └── index.html      Main SPA UI (86KB)
├── static/
│   └── batch.js        Batch mode JS (32KB)
├── docs/callback/      OAuth callback pages
├── output/             Generated content (timestamped dirs)
├── uploads/            User uploads
├── voices/             Voice samples
├── fonts/              NotoEmoji.ttf
├── music/              Background music files
├── kol/                KOL reference images
├── tests/              pytest tests
├── start.sh            Dev server launcher
├── Dockerfile          Container build
└── TODO.txt            Feature tracking
```

## Core Pipeline Flow

```
1. Extract    → extractor.py: Shopee URL → BookInfo (title, price, images)
2. Affiliate  → affiliate.py: AffiPad API → shortened tracking link
3. Review     → reviewer.py: Gemini generates platform-specific scripts
                 (social_post, hook, key_points, cta, hashtags)
4. TTS        → tts.py: ElevenLabs/gTTS → MP3 narration
5. Images     → download product images + imagegen.py AI lifestyle images
6. Video      → video/render.py: compose images + audio + subtitles + music → MP4
7. Publish    → poster.py: upload to FB/TikTok/YouTube (draft mode)
```

## Key Data Structures

### BookInfo (extractor.py)
```python
@dataclass
class BookInfo:
    title: str
    author: str
    description: str
    price: str | None
    image_url: str | None
    image_urls: list[str]
    shopee_url: str | None
    source: str  # "pdf" or "shopee"
    rating: float | None
    rating_count: int
    reviews: list[dict]
```

### PipelineInput / PipelineResult (pipeline.py)
```python
@dataclass
class PipelineInput:
    url: str
    audience: str
    custom_audience: dict | None
    affiliate_url: str
    word_count_fb: int  # ~150
    word_count_tk: int  # ~120
    image_urls: list[str]
    voice_type: str  # "elevenlabs" | "gtts"
    elevenlabs_voice_id: str
    platforms: list[str]  # ["facebook", "tiktok"]
```

### Review JSON output (per platform)
```json
{
  "social_post": "Full review text for posting",
  "review": "Shorter review variant",
  "hook": "Opening hook line",
  "key_points": ["point1", "point2"],
  "cta": "Call to action text",
  "hashtags": ["#tag1", "#tag2"]
}
```

### VideoInput (video/prepare.py)
Key fields: review_data, platform, selected_images, music_volume, aspect_ratio, voice_speed, subtitle_style, img_effect, show_intro/outro

## Environment Variables (.env)

- `GEMINI_API_KEY` — Google Gemini API
- `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` — TTS
- `AFFIPAD_API_KEY` / `AFFIPAD_TOOL_ID` — Affiliate link conversion
- `SHORTIO_API_KEY` / `SHORTIO_DOMAIN` — URL shortener
- `BITLY_API_KEY` — Fallback URL shortener
- `N8N_WEBHOOK_URL` — Automation webhook
- `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` — TikTok OAuth
- `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` — YouTube OAuth
- `FB_PAGE_ACCESS_TOKEN` — Facebook posting

## Audience/Persona System

Three built-in audiences in `config.py` (Vietnamese parents, students). Batch mode uses Gemini to suggest 2 custom personas per product, user picks 1.

## Batch Mode

1. User adds product cards (URL + affiliate + images)
2. System suggests personas per product
3. Parallel review generation (FB + TK simultaneously)
4. Parallel TTS generation
5. Video rendering (2 concurrent)
6. Publish buttons per video

## Output Naming Convention

`output/{YYYYMMDD_HHMMSS}_{suffix}`

Suffixes: `review.json`, `facebook.mp3`, `tiktok.mp3`, `facebook.mp4`, `tiktok.mp4`, `facebook.srt`, `images/`, `ai_images/`

## Testing

```bash
pytest tests/  # 11 tests covering importer, review errors, platform filtering, render guards, affiliate
```

## Running

```bash
./start.sh  # or: uvicorn app:app --host 0.0.0.0 --port 8000 --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem
```

## Current Status (May 2026)

**Working:** Full pipeline (extract → review → TTS → video → publish for FB/TikTok/YouTube), batch mode, Excel import, AI image generation, OAuth flows.

**In Progress:** TikTok app approval (submitted).

**TODO:** AccessTrade API integration, multi-account publishing, auto-posting scheduler, analytics dashboard, split app.py into routers.
