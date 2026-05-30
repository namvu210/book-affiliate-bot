"""Static page routes."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import AUDIENCES, DEFAULT_VOICE_SPEED

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "audiences": AUDIENCES, "default_voice_speed": DEFAULT_VOICE_SPEED, "default_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "")})


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/tiktok-demo", response_class=HTMLResponse)
async def tiktok_demo(request: Request):
    return templates.TemplateResponse("tiktok-demo.html", {"request": request})


@router.get("/movie", response_class=HTMLResponse)
async def movie_ad(request: Request):
    return templates.TemplateResponse("movie.html", {"request": request})
