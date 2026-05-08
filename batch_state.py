"""Batch job persistence — server-side state for batch processing."""

import json
import threading
from datetime import datetime
from pathlib import Path

BATCH_DIR = Path("batch_jobs")
BATCH_DIR.mkdir(exist_ok=True)
_lock = threading.Lock()


def create_batch(products: list[dict], settings: dict) -> str:
    """Create a new batch job. Returns batch ID."""
    batch_id = datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    job = {
        "id": batch_id,
        "created_at": datetime.now().isoformat(),
        "settings": settings,
        "products": products,
        "reviews": [],
    }
    _save(batch_id, job)
    return batch_id


def save_state(batch_id: str, reviews: list[dict]):
    """Save current batch state (reviews with all step results)."""
    job = _load(batch_id)
    if not job:
        # Create on-the-fly if no batch_id exists yet
        job = {"id": batch_id, "created_at": datetime.now().isoformat(), "settings": {}, "products": [], "reviews": []}
    job["reviews"] = reviews
    job["updated_at"] = datetime.now().isoformat()
    _save(batch_id, job)


def load_state(batch_id: str) -> dict | None:
    """Load batch job state."""
    return _load(batch_id)


def get_latest() -> dict | None:
    """Get the most recent batch job."""
    files = sorted(BATCH_DIR.glob("batch_*.json"), reverse=True)
    if files:
        return json.loads(files[0].read_text())
    return None


def list_batches(limit: int = 10) -> list[dict]:
    """List recent batch jobs (metadata only)."""
    files = sorted(BATCH_DIR.glob("batch_*.json"), reverse=True)[:limit]
    result = []
    for f in files:
        try:
            job = json.loads(f.read_text())
            result.append({
                "id": job["id"],
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "product_count": len(job.get("products", job.get("reviews", []))),
                "reviews_done": sum(1 for r in job.get("reviews", []) if r.get("reviewDone")),
                "assets_done": sum(1 for r in job.get("reviews", []) if r.get("assetsDone")),
            })
        except Exception:
            pass
    return result


def _save(batch_id: str, job: dict):
    with _lock:
        path = BATCH_DIR / f"{batch_id}.json"
        path.write_text(json.dumps(job, ensure_ascii=False, default=str))


def _load(batch_id: str) -> dict | None:
    path = BATCH_DIR / f"{batch_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None
