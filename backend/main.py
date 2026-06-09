"""FastAPI application entrypoint for EmberHeart Reborn.

Wires the DM engine, world sim, and memory behind one HTTP/WS surface and serves the
no-build web UI as static files. On startup it initialises the SQLite schema and, if
the kingdom-phase economy is enabled, runs a background tick loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core import db
from backend.core.config import settings
from backend.llm.client import get_llm

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("emberheart")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


async def _economy_loop() -> None:
    """Background kingdom-economy tick. No-op until a domain is ruled + enabled."""
    from backend.sim import economy

    while True:
        await asyncio.sleep(max(30, settings.economy_tick_seconds))
        try:
            if economy.is_enabled():
                economy.tick()
        except Exception:  # noqa: BLE001
            logger.exception("economy tick failed")


async def _idle_loop() -> None:
    """Background idle-skilling tick — accumulates resources while you're away."""
    from backend.sim import idle

    while True:
        await asyncio.sleep(15)
        try:
            idle.tick()
        except Exception:  # noqa: BLE001
            logger.exception("idle tick failed")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("database ready at %s", settings.db_path_resolved)
    from backend.dm.broker import broker
    broker.restore_feed()          # bring back the last beats after a restart
    tasks = [asyncio.create_task(_economy_loop()), asyncio.create_task(_idle_loop())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await get_llm().close()


app = FastAPI(title="EmberHeart Reborn", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Fail loudly with a clean envelope instead of leaking a stack trace."""
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        {"detail": str(exc), "type": exc.__class__.__name__, "path": request.url.path},
        status_code=500,
    )


# ------------------------------------------------------- always-fresh static assets
@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Make the browser revalidate HTML/JS/CSS each load (cheap 304s via ETag) so UI
    changes show up without a hard-refresh / PWA reinstall — the no-build app has no
    asset hashing of its own."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".webmanifest")):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ----------------------------------------------------------------- password gate
@app.middleware("http")
async def password_gate(request: Request, call_next):
    if settings.app_password:
        path = request.url.path
        open_paths = ("/healthz", "/api/health")
        if path.startswith("/api/") and path not in open_paths:
            if request.headers.get("X-App-Password") != settings.app_password:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


# --------------------------------------------------------------------- routers
from backend.api import (ascension, chat, combat, entities, gallery, hooks,  # noqa: E402
                         idle, journal, memory, mounts, play, world)

app.include_router(play.router)
app.include_router(world.router)
app.include_router(entities.router)
app.include_router(memory.router)
app.include_router(combat.router)
app.include_router(hooks.router)
app.include_router(chat.router)
app.include_router(idle.router)
app.include_router(ascension.router)
app.include_router(journal.router)
app.include_router(mounts.router)
app.include_router(gallery.router)


# ----------------------------------------------------------------------- health
@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/api/health")
async def api_health() -> dict:
    available = await get_llm().list_models()
    return {
        "ok": True,
        "ollama": await get_llm().health_check(),
        "models": available,
        "narration_model": settings.narration_model,
        "fallback_model": settings.fallback_model,
        "intimate_model": settings.intimate_model,
        "full_context": settings.full_context,
        # is the configured narration model actually pulled/reachable?
        "narration_ready": any(settings.narration_model in m for m in available),
    }


# --------------------------------------------------------------- static web UI
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.app_host, port=settings.app_port)


if __name__ == "__main__":
    run()
