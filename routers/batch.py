"""Batch orchestration routes."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request

from batch_state import _load, _save
from config import make_ts

router = APIRouter(prefix="/api/batch")


@router.post("/save")
async def batch_save(request: Request):
    """Save batch state to server."""
    from batch_state import save_state
    data = await request.json()
    batch_id = data.get("batch_id") or "batch_" + make_ts()
    save_state(batch_id, data.get("reviews", []))
    return {"batch_id": batch_id}


@router.get("/latest")
async def batch_latest():
    """Get the most recent batch state."""
    from batch_state import get_latest
    job = get_latest()
    return job or {"reviews": []}


@router.get("/list")
async def batch_list():
    """List recent batches."""
    from batch_state import list_batches
    return {"batches": list_batches()}


@router.post("/start")
async def batch_start(request: Request):
    """Start a new batch job with backend orchestration."""
    from batch_runner import run_personas, _running

    data = await request.json()
    batch_id = "batch_" + make_ts()
    job = {
        "id": batch_id,
        "status": "created",
        "settings": data.get("settings", {}),
        "products": [
            {"url": p.get("url", ""), "title": p.get("title", ""), "affiliate": p.get("affiliate", ""),
             "image_paths": p.get("image_paths", []), "steps": {}}
            for p in data.get("products", [])
        ],
    }
    _save(batch_id, job)

    task = asyncio.create_task(run_personas(batch_id))
    _running[batch_id] = task
    return {"batch_id": batch_id}


@router.get("/{batch_id}")
async def batch_get(batch_id: str):
    """Get batch job status."""
    from batch_runner import get_job
    job = get_job(batch_id)
    if not job:
        raise HTTPException(404, "Batch not found")
    return job


@router.post("/{batch_id}/confirm-personas")
async def batch_confirm_personas(batch_id: str, request: Request):
    """Confirm persona selections and start Phase 2."""
    from batch_runner import run_reviews_and_assets, _running

    data = await request.json()
    selections = data.get("selections", [])

    job = _load(batch_id)
    if not job:
        raise HTTPException(404, "Batch not found")

    for sel in selections:
        idx = sel["idx"]
        persona_idx = sel.get("persona_idx", 0)
        product = job["products"][idx]
        personas = product.get("steps", {}).get("persona", {}).get("result", [])
        if personas and persona_idx < len(personas):
            product["selected_persona"] = personas[persona_idx]
    _save(batch_id, job)

    task = asyncio.create_task(run_reviews_and_assets(batch_id))
    _running[batch_id] = task
    return {"status": "processing"}


@router.post("/{batch_id}/generate-videos")
async def batch_generate_videos(batch_id: str):
    """Start Phase 3: video generation."""
    from batch_runner import run_videos, _running

    task = asyncio.create_task(run_videos(batch_id))
    _running[batch_id] = task
    return {"status": "videos_running"}


@router.post("/{batch_id}/retry/{idx}/{step}")
async def batch_retry(batch_id: str, idx: int, step: str):
    """Retry a specific step for a specific product."""
    from batch_runner import retry_step
    await retry_step(batch_id, idx, step)
    return {"status": "ok"}
