# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A FastAPI app that automates Vietnamese-language affiliate content creation for social media (Facebook, TikTok, YouTube). Given a Shopee product URL, it extracts product info, generates AI review scripts via Gemini, synthesizes voice narration, renders short-form videos, and publishes to platforms.

**Language:** All UI, prompts, and generated content are in Vietnamese.
**Runtime:** Python 3.13, macOS dev environment.

## Commands

```bash
# Run dev server (HTTPS with self-signed certs, auto-reload, opens browser)
./start.sh

# Or manually:
uvicorn app:app --reload --port 8000 --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem

# Tests
pytest tests/ -q --tb=short

# Single test file or function
pytest tests/test_persona_retry.py -q
pytest tests/test_importer.py::test_parse_valid_xlsx -q

# Ship (stages all, runs tests, commits, pushes)
./ship.sh "commit message"

# Docker
docker build -t book-bot . && docker run -p 8000:8000 --env-file .env book-bot
```

System dependency: `ffmpeg` (required for video rendering and audio speed adjustment).

## Architecture

The core pipeline flows through these stages in order:

```
extractor.py → affiliate.py → reviewer.py → tts.py → imagegen.py → video/render.py → poster.py
```

**Orchestration layer:** `pipeline.py` ties the steps together for single-product generation. `batch_runner.py` handles multi-product batch jobs with parallelism (persona suggestion → review → TTS → video). `batch_state.py` provides load/save helpers for batch job JSON files persisted in `batch_jobs/`.

**Web layer:** `app.py` is the FastAPI entrypoint (lifespan, middleware, router mounts). Routes live in `routers/`:
- `pages.py` — static HTML pages
- `extract.py` — product extraction (Shopee, PDF, bookmarklet, Excel import)
- `review.py` — review generation (single, batch, regen, preview)
- `assets.py` — TTS, images, AI images, video rendering
- `batch.py` — batch orchestration (`/api/batch/` prefix)
- `schedule.py` — scheduler CRUD
- `platforms.py` — OAuth, publish, history, settings
- `templates.py` — video template CRUD (`/api/templates/` prefix)
- `api.py` — misc APIs: models, music, voices (`/api/` prefix)

The frontend is vanilla JS in `templates/index.html` (single-page app) with batch mode logic in `static/batch.js`.

**Scheduler:** `scheduler.py` + lifespan loop in `app.py` checks every 60s for posts scheduled at optimal Vietnam time slots (08:30, 12:00, 19:00, 21:30).

**Video package** (`video/`): `prepare.py` defines `VideoInput` and orchestrates rendering; `render.py` does MoviePy composition; `effects.py` has image animations (ken burns, zoom, pan); `text.py` handles subtitle overlays; `body.py` generates body-motion video clips; `beats.py` handles beat-synced effects; `media.py` has media helpers (PDF cover extraction).

**Auth:** `auth.py` manages OAuth2 flows for TikTok, YouTube, Facebook. Tokens stored in `tokens.json`.

## Key Conventions

- Timestamps used as output identifiers: `YYYYMMDD_HHMMSSff` (17 chars). Built by `config.make_ts()`.
- Output files: `output/{timestamp}_{suffix}` where suffix is `review.json`, `facebook.mp3`, `tiktok.mp4`, etc.
- The `config.py` module is the central import for env vars, constants, and small utilities (`strip_emoji`, `make_ts`, `output_path`).
- Gemini calls go through `reviewer.generate_json()` which handles retries (exponential backoff on 503/429) and JSON repair. Uses `google-genai` SDK (not the older `google-generativeai`). Default model: `gemini-2.5-flash`, switchable at runtime via `reviewer.set_model()`.
- Three TTS engines: ElevenLabs (primary, expressive), edge-tts (Microsoft, free Vietnamese voices), and gTTS (Google, fallback). Speed is controlled in percentage (100 = normal, 140 = default fast).
- Three built-in audience personas in `config.AUDIENCES`; batch mode auto-suggests custom personas via Gemini.

## Testing

Tests use `sys.path.insert(0, ".")` for imports — run pytest from the project root. Tests mock external APIs (Gemini, ElevenLabs) via `unittest.mock.patch`. No fixtures file; each test is self-contained.

## Environment

All secrets in `.env` (not committed). Key ones: `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `AFFIPAD_API_KEY`, `TIKTOK_CLIENT_KEY/SECRET`, `YOUTUBE_CLIENT_ID/SECRET`, `FB_PAGE_ACCESS_TOKEN`.
