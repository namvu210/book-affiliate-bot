"""Admin prompt management routes — CRUD, A/B testing, version history."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin/prompts")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def admin_prompts_page(request: Request):
    from prompt_manager import list_presets, get_ab_test_raw
    return templates.TemplateResponse("admin_prompts.html", {
        "request": request,
        "presets": list_presets(),
        "ab_test": get_ab_test_raw(),
    })


@router.get("/api/list")
async def api_list_presets():
    from prompt_manager import list_presets
    return {"presets": list_presets()}


@router.get("/api/history")
async def api_history(style_id: str = ""):
    from prompt_manager import get_history
    return {"history": get_history(style_id or None)}


@router.get("/api/ab-test")
async def api_get_ab_test():
    from prompt_manager import get_ab_test_raw
    return get_ab_test_raw()


@router.get("/api/{style_id}")
async def api_get_preset(style_id: str):
    from prompt_manager import load_preset
    preset = load_preset(style_id)
    if not preset:
        raise HTTPException(404, "Preset not found")
    return preset


@router.post("/api/save")
async def api_save_preset(
    style_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    template: str = Form(...),
):
    from prompt_manager import save_preset
    return save_preset(style_id, name, description, template)


@router.delete("/api/{style_id}")
async def api_delete_preset(style_id: str):
    from prompt_manager import delete_preset
    if not delete_preset(style_id):
        raise HTTPException(404, "Preset not found")
    return {"status": "ok"}


@router.post("/api/restore")
async def api_restore_version(style_id: str = Form(...), version: int = Form(...)):
    from prompt_manager import restore_version
    result = restore_version(style_id, version)
    if not result:
        raise HTTPException(404, "Version not found")
    return result


@router.post("/api/ab-test/start")
async def api_start_ab_test(variant_a: str = Form(...), variant_b: str = Form(...)):
    from prompt_manager import start_ab_test, load_preset
    if not load_preset(variant_a):
        raise HTTPException(400, f"Variant A '{variant_a}' not found")
    if not load_preset(variant_b):
        raise HTTPException(400, f"Variant B '{variant_b}' not found")
    return start_ab_test(variant_a, variant_b)


@router.post("/api/ab-test/stop")
async def api_stop_ab_test():
    from prompt_manager import stop_ab_test
    return stop_ab_test()
