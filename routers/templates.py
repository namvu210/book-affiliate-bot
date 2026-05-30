"""Video template CRUD routes."""

import json
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

router = APIRouter(prefix="/api/templates")

TEMPLATE_DIR = Path("templates_video")
TEMPLATE_DIR.mkdir(exist_ok=True)


@router.get("")
async def list_templates():
    templates = []
    for f in sorted(TEMPLATE_DIR.glob("*.json")):
        templates.append({"name": f.stem, "file": f.name})
    return {"templates": templates}


@router.post("")
async def save_template(name: str = Form(...), config: str = Form(...)):
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
    (TEMPLATE_DIR / f"{safe_name}.json").write_text(config)
    return {"status": "ok", "name": safe_name}


@router.get("/{name}")
async def load_template(name: str):
    f = TEMPLATE_DIR / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "Template không tồn tại")
    return json.loads(f.read_text())


@router.delete("/{name}")
async def delete_template(name: str):
    f = TEMPLATE_DIR / f"{name}.json"
    f.unlink(missing_ok=True)
    return {"status": "ok"}
