# Phase C: Backend Batch Orchestration — Design Doc

## Overview

Move batch step execution from frontend JS to backend async tasks.
Frontend submits a batch job, then polls for progress.

## Current Flow (frontend orchestrates)

```
Frontend (batch.js):
  for each product:
    POST /suggest-personas → wait
  show persona UI → user confirms
  for each product:
    POST /batch-review → wait
  for each product:
    POST /batch-assets → wait (TTS + images + AI)
  for each product (2 concurrent):
    POST /generate-video → wait
```

## Proposed Flow (backend orchestrates)

```
Frontend:
  POST /api/batch/start → {batch_id}
  Poll GET /api/batch/{id} every 3s → render progress
  User actions: retry, skip, confirm personas, proceed to videos

Backend:
  POST /api/batch/start
    → Creates batch job
    → Starts background task: run_batch(batch_id)

  Background task:
    Phase 1: Personas (sequential, ~3s each)
      → Update job state after each product
      → Pause at end, wait for user confirmation

    Phase 2: Reviews + Assets (after user confirms personas)
      POST /api/batch/{id}/proceed
      → For each product (controlled concurrency):
        - Generate review
        - Generate audio (ElevenLabs, no fallback)
        - Save images
        - Generate AI images
      → Update state per product per step

    Phase 3: Videos (after user confirms step 2)
      POST /api/batch/{id}/generate-videos
      → 2 concurrent video renders
      → Update state per video
```

## API Endpoints

```
POST /api/batch/start
  Body: { products: [{url, affiliate, images}], settings: {voice, speed, word_count} }
  Returns: { batch_id }

GET /api/batch/{id}
  Returns: Full job state (products, steps, progress)

POST /api/batch/{id}/confirm-personas
  Body: { selections: [{product_idx, persona_idx}] }
  → Triggers Phase 2

POST /api/batch/{id}/proceed-videos
  → Triggers Phase 3

POST /api/batch/{id}/retry/{product_idx}/{step}
  step: "persona" | "review" | "audio" | "ai_images" | "video"
  → Re-runs that step for that product

POST /api/batch/{id}/cancel
  → Stops processing
```

## Job State Schema

```json
{
  "id": "batch_20260509_020000",
  "status": "personas_done",  // created | personas_running | personas_done | processing | done | cancelled
  "settings": { "voice_type": "elevenlabs", "voice_speed": 140, "word_count": 120 },
  "products": [
    {
      "url": "...",
      "title": "...",
      "affiliate": "...",
      "image_paths": [...],
      "persona_options": [...],       // from step 1
      "selected_persona": {...},      // user choice
      "steps": {
        "persona":   { "status": "done", "result": [...] },
        "review":    { "status": "done", "result": {...} },
        "audio":     { "status": "error", "error": "quota_exceeded" },
        "images":    { "status": "done", "result": [...] },
        "ai_images": { "status": "done", "result": [...], "expected": 4, "generated": 3 },
        "video":     { "status": "pending" }
      }
    }
  ]
}
```

## Background Task Implementation

```python
# batch_runner.py
import asyncio
from batch_state import save_state, load_state

async def run_batch_personas(batch_id: str):
    """Run persona suggestions for all products."""
    job = load_state(batch_id)
    for i, product in enumerate(job["products"]):
        try:
            personas = await suggest_personas(product["title"])
            product["steps"]["persona"] = {"status": "done", "result": personas}
        except Exception as e:
            product["steps"]["persona"] = {"status": "error", "error": str(e)}
        save_state(batch_id, job)  # save after each product
    job["status"] = "personas_done"
    save_state(batch_id, job)

async def run_batch_assets(batch_id: str):
    """Run reviews + assets for all confirmed products."""
    job = load_state(batch_id)
    semaphore = asyncio.Semaphore(2)  # max 2 concurrent

    async def process_one(product):
        async with semaphore:
            # Review
            # Audio
            # Images
            # AI Images
            save_state(batch_id, job)

    await asyncio.gather(*[process_one(p) for p in job["products"]])
```

## Concurrency Control

| Step | Max concurrent | Rate limit |
|------|---------------|------------|
| Personas (flash-lite) | 3 | 300 RPM (Tier 1) |
| Reviews (flash-lite) | 3 | 300 RPM |
| Audio (ElevenLabs) | 1 | Quota-based |
| AI Images (flash-image) | 2 | 10 RPM |
| Video render | 2 | CPU-bound |

## Frontend Changes

```js
// Replace orchestration with polling
async function startBatch(products, settings) {
    var resp = await fetch('/api/batch/start', {method:'POST', body: JSON.stringify({products, settings})});
    var {batch_id} = await resp.json();
    pollBatchStatus(batch_id);
}

function pollBatchStatus(batchId) {
    setInterval(async function() {
        var resp = await fetch('/api/batch/' + batchId);
        var job = await resp.json();
        renderBatchProgress(job);
        if (job.status === 'done' || job.status === 'cancelled') clearInterval(this);
    }, 3000);
}
```

## Migration Path

1. Add `batch_runner.py` with async task functions
2. Add new API endpoints (keep old ones working)
3. Add "New Batch Mode" toggle in UI (A/B test)
4. Once stable, remove old frontend orchestration

## Estimated Effort

- batch_runner.py: ~150 lines
- API endpoints: ~80 lines
- Frontend polling UI: ~100 lines
- Testing: ~50 lines
- Total: ~380 lines, ~2-3 hours
