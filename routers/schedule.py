"""Scheduler routes — queue, cancel, reschedule posts."""

import json

from fastapi import APIRouter, Form

router = APIRouter()


@router.post("/schedule")
async def schedule_post(
    review_json: str = Form(...),
    video_url: str = Form(""),
    platform: str = Form("all"),
    page_id: str = Form(""),
    slot: str = Form(""),
):
    """Schedule a video for auto-posting at optimal time."""
    from scheduler import add_job, get_slots
    data = json.loads(review_json)
    job = add_job(data, video_url, platform, page_id, slot)
    return {"status": "ok", "job_id": job["id"], "slot": job["slot"], "slots": get_slots()}


@router.get("/api/schedule")
async def get_schedule():
    """List all scheduled and recent jobs."""
    from scheduler import get_all, get_slots
    jobs = get_all()
    return {"jobs": jobs, "slots": get_slots()}


@router.post("/api/schedule/cancel")
async def cancel_scheduled(job_id: str = Form(...)):
    """Cancel a pending scheduled job."""
    from scheduler import cancel_job
    if cancel_job(job_id):
        return {"status": "ok"}
    return {"status": "error", "message": "Job not found or already published"}


@router.post("/api/schedule/slots")
async def update_slots(slot: str = Form(...)):
    """Set custom posting time slot (HH:MM). Added to the 4 fixed slots."""
    from scheduler import set_custom_slot, get_slots
    set_custom_slot(slot.strip())
    return {"status": "ok", "slots": get_slots()}


@router.post("/api/schedule/reschedule")
async def reschedule(job_id: str = Form(...), slot: str = Form(...)):
    """Reschedule a missed/pending job to a new slot."""
    from scheduler import reschedule_job
    if reschedule_job(job_id, slot):
        return {"status": "ok"}
    return {"status": "error", "message": "Job not found"}


@router.post("/api/schedule/publish-now")
async def publish_scheduled_now(job_id: str = Form(...)):
    """Immediately publish a scheduled/missed job."""
    from scheduler import _load_schedule, _mark_done, _mark_failed
    from poster import publish, build_post_request
    jobs = _load_schedule()
    job = next((j for j in jobs if j["id"] == job_id and j["status"] in ("pending", "failed")), None)
    if not job:
        return {"status": "error", "message": "Job not found"}
    try:
        from auth import get_platform_status
        data = job["review_data"]
        platform = job["platform"]
        if platform == "all":
            status = get_platform_status()
            platform_list = [p for p in ["facebook", "instagram", "tiktok", "youtube"] if status.get(p, {}).get("connected")]
            if not platform_list:
                platform_list = ["facebook"]
        else:
            platform_list = [platform]
        req = build_post_request(data, job["video_url"], platform_list[0])
        req.platforms = platform_list
        req.page_id = job.get("page_id", "")
        results = await publish(req)
        successes = [r for r in results if r.success]
        if successes:
            _mark_done(job["id"])
            return {"status": "ok", "message": " | ".join(r.message for r in successes)}
        else:
            msg = " | ".join(r.message for r in results)
            _mark_failed(job["id"], msg)
            return {"status": "error", "message": msg}
    except Exception as e:
        _mark_failed(job["id"], str(e))
        return {"status": "error", "message": str(e)}
