"""Post scheduler — queue videos for optimal time slots."""

import json
import threading
import asyncio
from datetime import datetime, time
from pathlib import Path

from config import log

SCHEDULE_FILE = Path("schedule.json")
SLOTS_FILE = Path("schedule_slots.json")
_lock = threading.Lock()

# Fixed optimal posting slots (Vietnam market) + 1 custom
FIXED_SLOTS = ["07:00", "12:00", "19:30", "21:30"]


def get_custom_slot() -> str:
    if SLOTS_FILE.exists():
        return json.loads(SLOTS_FILE.read_text()).get("custom", "")
    return ""


def set_custom_slot(slot: str):
    SLOTS_FILE.write_text(json.dumps({"custom": slot}))


def get_slots() -> list[str]:
    custom = get_custom_slot()
    slots = FIXED_SLOTS[:]
    if custom and custom not in slots:
        slots.append(custom)
    return sorted(slots)


def _load_schedule() -> list[dict]:
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())
    return []


def _save_schedule(jobs: list[dict]):
    with _lock:
        SCHEDULE_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2))


def add_job(review_data: dict, video_url: str, platform: str, page_id: str = "", slot: str = "") -> dict:
    """Add a video to the posting queue. slot='' means next available."""
    if not slot:
        slot = _next_slot()
    job = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "review_data": review_data,
        "video_url": video_url,
        "platform": platform,
        "page_id": page_id,
        "slot": slot,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "published_at": None,
    }
    jobs = _load_schedule()
    jobs.append(job)
    _save_schedule(jobs)
    log.info(f"Scheduled: {platform} at {slot}")
    return job


def get_pending() -> list[dict]:
    """Return all pending jobs."""
    return [j for j in _load_schedule() if j["status"] == "pending"]


def get_missed() -> list[dict]:
    """Return pending jobs whose slot has already passed today (missed)."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    missed = []
    for j in _load_schedule():
        if j["status"] != "pending":
            continue
        # If slot time has passed by more than 5 min, it's missed
        slot = j.get("slot", "")
        if slot and slot < current_time:
            sh, sm = int(slot.split(":")[0]), int(slot.split(":")[1])
            slot_time = now.replace(hour=sh, minute=sm, second=0)
            if (now - slot_time).total_seconds() > 300:
                missed.append(j)
    return missed


def get_all() -> list[dict]:
    """Return all jobs."""
    return _load_schedule()


def cancel_job(job_id: str) -> bool:
    """Cancel a pending job."""
    jobs = _load_schedule()
    for j in jobs:
        if j["id"] == job_id and j["status"] == "pending":
            j["status"] = "cancelled"
            _save_schedule(jobs)
            return True
    return False


def reschedule_job(job_id: str, new_slot: str) -> bool:
    """Reschedule a pending/missed job to a new slot."""
    jobs = _load_schedule()
    for j in jobs:
        if j["id"] == job_id and j["status"] == "pending":
            j["slot"] = new_slot
            _save_schedule(jobs)
            return True
    return False


def _next_slot() -> str:
    """Find the next upcoming slot today, or first slot tomorrow."""
    now = datetime.now().strftime("%H:%M")
    slots = get_slots()
    for s in slots:
        if s > now:
            return s
    return slots[0]  # wrap to first slot (tomorrow)


def _mark_done(job_id: str):
    """Mark job as published."""
    jobs = _load_schedule()
    for j in jobs:
        if j["id"] == job_id:
            j["status"] = "published"
            j["published_at"] = datetime.now().isoformat()
    _save_schedule(jobs)


def _mark_failed(job_id: str, error: str):
    """Mark job as failed (will retry next matching slot)."""
    jobs = _load_schedule()
    for j in jobs:
        if j["id"] == job_id:
            j["status"] = "pending"  # keep pending for retry
            j["last_error"] = error
    _save_schedule(jobs)


async def check_and_publish():
    """Check if any pending jobs match the current time slot. Called every 60s."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")

    # Only fire within ±2 min of a slot
    matching_slot = None
    for s in get_slots():
        sh, sm = int(s.split(":")[0]), int(s.split(":")[1])
        slot_time = now.replace(hour=sh, minute=sm, second=0)
        diff = abs((now - slot_time).total_seconds())
        if diff <= 120:
            matching_slot = s
            break

    if not matching_slot:
        return

    pending = [j for j in _load_schedule() if j["status"] == "pending" and j["slot"] == matching_slot]
    if not pending:
        return

    log.info(f"Scheduler: {len(pending)} jobs for slot {matching_slot}")

    from poster import publish, build_post_request

    for job in pending:
        try:
            data = job["review_data"]
            req = build_post_request(data, job["video_url"], job["platform"])
            req.platforms = [job["platform"]]
            req.page_id = job.get("page_id", "")
            results = await publish(req)
            if results and results[0].success:
                _mark_done(job["id"])
                log.info(f"Scheduler: published {job['platform']} ✅")
                # Record in history
                from history import record_publish
                book = data.get("book", {})
                plat_data = data.get(job["platform"], {})
                post_url = ""
                if results[0].post_id:
                    pid = results[0].post_id
                    if job["platform"] == "facebook":
                        post_url = f"https://www.facebook.com/reel/{pid}"
                    elif job["platform"] == "tiktok":
                        post_url = f"https://www.tiktok.com/@/video/{pid}"
                    elif job["platform"] == "youtube":
                        post_url = f"https://youtube.com/shorts/{pid}"
                record_publish(
                    book.get("shopee_url", ""), book.get("shopee_url", ""),
                    job["platform"], book.get("title", ""),
                    persona=data.get("audience_name", ""),
                    hook=plat_data.get("hook", ""),
                    cta=plat_data.get("cta", ""),
                    review_text=plat_data.get("social_post", ""),
                    video_path=job["video_url"],
                    post_url=post_url,
                )
            else:
                msg = results[0].message if results else "Unknown error"
                _mark_failed(job["id"], msg)
                log.warning(f"Scheduler: failed {job['platform']}: {msg}")
        except Exception as e:
            _mark_failed(job["id"], str(e))
            log.warning(f"Scheduler: error {job['platform']}: {e}")
