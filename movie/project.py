"""Movie project persistence — JSON file per project."""

import json
import threading
from datetime import datetime
from pathlib import Path

from config import make_ts

PROJECT_DIR = Path("movie_projects")
PROJECT_DIR.mkdir(exist_ok=True)
_lock = threading.Lock()


def create_project(product_title: str, kol_ids: list[str], product_url: str = "", product_images: list[str] = None, affiliate_link: str = "") -> dict:
    project_id = make_ts()
    project = {
        "id": project_id,
        "product_title": product_title,
        "product_url": product_url,
        "affiliate_link": affiliate_link,
        "product_images": product_images or [],
        "kol_ids": kol_ids,
        "screenplay": None,
        "scene_image": None,
        "segment_videos": {},
        "video_clip": None,
        "extended_video": None,
        "final_video": None,
        "status": "draft",
        "created_at": datetime.now().isoformat(),
    }
    _save(project_id, project)
    return project


def get_project(project_id: str) -> dict | None:
    return _load(project_id)


def update_project(project_id: str, updates: dict) -> dict | None:
    project = _load(project_id)
    if not project:
        return None
    project.update(updates)
    project["updated_at"] = datetime.now().isoformat()
    _save(project_id, project)
    return project


def list_projects(limit: int = 20) -> list[dict]:
    files = sorted(PROJECT_DIR.glob("*.json"), reverse=True)[:limit]
    result = []
    for f in files:
        try:
            p = json.loads(f.read_text())
            result.append({
                "id": p["id"],
                "product_title": p.get("product_title", ""),
                "status": p.get("status", "draft"),
                "created_at": p.get("created_at", ""),
                "kol_ids": p.get("kol_ids", []),
            })
        except Exception:
            pass
    return result


def _save(project_id: str, project: dict):
    with _lock:
        path = PROJECT_DIR / f"{project_id}.json"
        path.write_text(json.dumps(project, ensure_ascii=False, default=str))


def _load(project_id: str) -> dict | None:
    path = PROJECT_DIR / f"{project_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None
