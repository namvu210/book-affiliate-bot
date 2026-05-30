"""Product Affiliate Bot — Extract, Review, Voice & Video."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import OUTPUT_DIR, UPLOAD_DIR

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

_log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: launch scheduler loop. Shutdown: cancel it."""
    from scheduler import check_and_publish

    app.state.last_shopee_data = None

    async def _scheduler_loop():
        while True:
            try:
                await check_and_publish()
            except Exception as e:
                _log.warning(f"Scheduler tick error: {e}")
            await asyncio.sleep(60)

    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Product Affiliate Bot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class _PollFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "poll-shopee-data" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_PollFilter())
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# --- Routers ---
from routers import pages, extract, review, assets, batch, schedule, platforms, templates, api, prompts, movie

app.include_router(pages.router)
app.include_router(extract.router)
app.include_router(review.router)
app.include_router(assets.router)
app.include_router(batch.router)
app.include_router(schedule.router)
app.include_router(platforms.router)
app.include_router(templates.router)
app.include_router(api.router)
app.include_router(prompts.router)
app.include_router(movie.router)
app.mount("/kol_profiles", StaticFiles(directory="kol_profiles"), name="kol_profiles")


