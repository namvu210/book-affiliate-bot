"""KOL profile management — filesystem-based CRUD for character reference photos."""

import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

KOL_DIR = Path("kol_profiles")
KOL_DIR.mkdir(exist_ok=True)
_lock = threading.Lock()


def list_profiles() -> list[dict]:
    profiles = []
    for d in sorted(KOL_DIR.iterdir()):
        if d.is_dir() and (d / "profile.json").exists():
            try:
                p = json.loads((d / "profile.json").read_text())
                p["id"] = d.name
                p["turnaround_images"] = _get_image_urls(d.name)
                profiles.append(p)
            except Exception:
                pass
    return profiles


def get_profile(kol_id: str) -> dict | None:
    path = KOL_DIR / kol_id / "profile.json"
    if not path.exists():
        return None
    p = json.loads(path.read_text())
    p["id"] = kol_id
    p["turnaround_images"] = _get_image_urls(kol_id)
    return p


def create_profile(name: str, description: str, images: list[bytes]) -> dict:
    kol_id = uuid.uuid4().hex[:12]
    profile_dir = KOL_DIR / kol_id
    profile_dir.mkdir(parents=True, exist_ok=True)

    profile = {
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "image_count": len(images),
    }

    for i, img_bytes in enumerate(images):
        img_path = profile_dir / f"ref_{i:02d}.jpg"
        img = Image.open(__import__("io").BytesIO(img_bytes))
        img = img.convert("RGB")
        if max(img.size) > 1536:
            img.thumbnail((1536, 1536), Image.LANCZOS)
        img.save(img_path, "JPEG", quality=90)

    with _lock:
        (profile_dir / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False)
        )

    profile["id"] = kol_id
    profile["turnaround_images"] = _get_image_urls(kol_id)
    return profile


def delete_profile(kol_id: str) -> bool:
    profile_dir = KOL_DIR / kol_id
    if not profile_dir.exists():
        return False
    with _lock:
        shutil.rmtree(profile_dir)
    return True


def get_reference_paths(kol_id: str) -> list[str]:
    profile_dir = KOL_DIR / kol_id
    if not profile_dir.exists():
        return []
    return sorted(str(p) for p in profile_dir.glob("ref_*.jpg"))


def _get_image_urls(kol_id: str) -> list[str]:
    profile_dir = KOL_DIR / kol_id
    return sorted(
        f"/kol_profiles/{kol_id}/{p.name}"
        for p in profile_dir.glob("ref_*.jpg")
    )
