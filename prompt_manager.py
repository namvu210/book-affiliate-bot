"""Prompt template management — load, render, A/B split, version history."""

import json
import random
import re
from datetime import datetime
from pathlib import Path

import yaml

PROMPTS_DIR = Path("prompts")
HISTORY_FILE = PROMPTS_DIR / "history.json"
AB_TEST_FILE = PROMPTS_DIR / "ab_test.json"


def _ensure_dir():
    PROMPTS_DIR.mkdir(exist_ok=True)


def list_presets() -> list[dict]:
    _ensure_dir()
    presets = []
    for f in sorted(PROMPTS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            presets.append({"id": data.get("id", f.stem), "name": data.get("name", f.stem), "description": data.get("description", "")})
        except Exception:
            continue
    return presets


def load_preset(style_id: str) -> dict | None:
    _ensure_dir()
    path = PROMPTS_DIR / f"{style_id}.yaml"
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return None


def save_preset(style_id: str, name: str, description: str, template: str) -> dict:
    _ensure_dir()
    path = PROMPTS_DIR / f"{style_id}.yaml"
    existing = load_preset(style_id)
    version = (existing.get("version", 0) + 1) if existing else 1

    data = {
        "id": style_id,
        "name": name,
        "description": description,
        "version": version,
        "template": template,
    }
    path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
    _append_history(style_id, "update" if version > 1 else "create", version, template)
    return data


def delete_preset(style_id: str) -> bool:
    path = PROMPTS_DIR / f"{style_id}.yaml"
    if not path.exists():
        return False
    path.unlink()
    _append_history(style_id, "delete", 0, "")
    return True


def render_template(template: str, variables: dict) -> str:
    def _replace(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", _replace, template)


def resolve_style(requested: str | None) -> str:
    if requested and requested != "auto":
        return requested
    ab = get_ab_test()
    if ab and ab.get("active"):
        return random.choice([ab["variant_a"], ab["variant_b"]])
    return "product-based"


def get_ab_test() -> dict | None:
    if not AB_TEST_FILE.exists():
        return None
    try:
        data = json.loads(AB_TEST_FILE.read_text(encoding="utf-8"))
        return data if data.get("active") else None
    except Exception:
        return None


def get_ab_test_raw() -> dict:
    if not AB_TEST_FILE.exists():
        return {"active": False, "variant_a": None, "variant_b": None, "started_at": None, "stopped_at": None}
    try:
        return json.loads(AB_TEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "variant_a": None, "variant_b": None, "started_at": None, "stopped_at": None}


def start_ab_test(variant_a: str, variant_b: str) -> dict:
    _ensure_dir()
    data = {
        "active": True,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "started_at": datetime.now().isoformat(),
        "stopped_at": None,
    }
    AB_TEST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def stop_ab_test() -> dict:
    data = get_ab_test_raw()
    data["active"] = False
    data["stopped_at"] = datetime.now().isoformat()
    AB_TEST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_history(style_id: str | None = None) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        entries = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if style_id:
        entries = [e for e in entries if e.get("style_id") == style_id]
    return entries


def restore_version(style_id: str, version: int) -> dict | None:
    entries = get_history(style_id)
    target = next((e for e in entries if e.get("version") == version), None)
    if not target:
        return None
    existing = load_preset(style_id)
    name = existing.get("name", style_id) if existing else style_id
    description = existing.get("description", "") if existing else ""
    return save_preset(style_id, name, description, target["content_snapshot"])


def _append_history(style_id: str, action: str, version: int, content: str):
    _ensure_dir()
    entries = []
    if HISTORY_FILE.exists():
        try:
            entries = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "style_id": style_id,
        "action": action,
        "version": version,
        "content_snapshot": content,
    })
    HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
