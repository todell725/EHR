"""Play loop endpoints — the live DM interaction surface.

`/api/play/ws` streams a turn token-by-token (the UI shows live narration, then
snaps to the parsed sections on the final `result` event). `/api/play/action` is the
buffered fallback. Session endpoints handle the "Previously on" recap + faction tick.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core import backups
from backend.core.config import settings
from backend.core.models import PlayAction
from backend.dm import orchestrator
from backend.dm.broker import broker, last_persisted
from backend.sim import factions

router = APIRouter(prefix="/api", tags=["play"])
logger = logging.getLogger("emberheart.api.play")

_warm_tasks: set = set()


def _fire_warm(model: str | None) -> None:
    """Warm a model in the background so its cold start happens before play, not during."""
    task = asyncio.create_task(orchestrator.warm_model(model))
    _warm_tasks.add(task)
    task.add_done_callback(_warm_tasks.discard)


@router.websocket("/play/ws")
async def play_ws(ws: WebSocket) -> None:
    # The HTTP password middleware doesn't cover WebSockets — gate here via ?pw=.
    if settings.app_password and ws.query_params.get("pw") != settings.app_password:
        await ws.close(code=1008)
        return
    await ws.accept()
    q = broker.subscribe()

    # Catch-up: replay recent finished beats (deduped client-side by seq) so a (re)connecting
    # or freshly-loaded client gets everything it missed — not just the single last turn.
    async def _replay(turn: dict) -> None:
        await ws.send_json({"type": "replay_start", "seq": turn["seq"],
                            "action": turn["action"], "status": turn["status"]})
        for ev in turn["events"]:
            await ws.send_json(ev)
        if turn["status"] == "done":
            await ws.send_json({"type": "turn_done", "seq": turn["seq"]})

    replayed = set()
    for turn in list(broker.recent):
        await _replay(turn)
        replayed.add(turn["seq"])
    cur = broker.snapshot()
    if cur and cur["seq"] not in replayed:   # an in-flight (running) turn not yet in recent
        await _replay(cur)

    async def sender() -> None:
        while True:
            await ws.send_json(await q.get())

    send_task = asyncio.create_task(sender())
    try:
        while True:
            data = await ws.receive_json()
            action = (data or {}).get("action", "").strip()
            pc_id = (data or {}).get("pc_id")
            if not action:
                await ws.send_json({"type": "error", "message": "empty action"})
                continue
            started = await broker.submit(action, pc_id)
            if not started:
                await ws.send_json({"type": "notice", "message": "A turn is already underway."})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("play_ws error")
    finally:
        send_task.cancel()
        broker.unsubscribe(q)


@router.get("/play/state")
def play_state() -> dict:
    """REST recovery: the in-flight turn (if any) + the last persisted result."""
    cur = broker.snapshot()
    return {
        "current": ({"seq": cur["seq"], "status": cur["status"], "action": cur["action"]}
                    if cur else None),
        "last": last_persisted(),
    }


@router.post("/play/action")
async def play_action(body: PlayAction) -> dict:
    """Buffered fallback: run the turn through the BROKER and wait for the result.
    Calling the orchestrator directly here used to skip the one-turn-at-a-time guard,
    the replay buffer, and feed persistence — a second caller could mutate the world
    mid-turn and the beat vanished from reconnecting clients."""
    started = await broker.submit(body.text, body.pc_id)
    if not started:
        return {"ok": False, "detail": "a turn is already underway"}
    turn = broker.current
    deadline = asyncio.get_event_loop().time() + broker.overall_timeout + 60
    while turn["status"] == "running" and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.25)
    result = next((e for e in turn["events"] if e["type"] == "result"), None)
    if result is None:
        error = next((e for e in turn["events"] if e["type"] == "error"), None)
        return {"ok": False, "detail": (error or {}).get("message", "turn failed")}
    return result


@router.post("/play/submit")
async def play_submit(body: PlayAction) -> dict:
    """Enqueue a turn through the broker so it STREAMS into the live feed (used by the
    quest 'pick this up' buttons and any out-of-composer nudge). Returns ok=False if a
    turn is already running."""
    started = await broker.submit(body.text, body.pc_id)
    return {"ok": started}


class InjectBeat(BaseModel):
    narrative: str
    suggestions: list[dict] = []
    applied: list[str] = []
    mechanics: list[str] = []   # optional `TAG: args` lines applied through the trust boundary


def apply_inject_mechanics(raw_lines: list[str]) -> list[str]:
    """Apply an authored beat's state changes through the SAME `apply_mechanics` boundary
    a model turn uses — so injected prose and the game ledger can't fall out of sync, and
    a typo'd tag is rejected/noted (and surfaced) rather than silently wrong."""
    from backend.dm import mechanics, parser

    mechs, _ = parser._parse_mechanics("\n".join(raw_lines))
    res = mechanics.apply_mechanics(mechs)
    display = list(res["applied"])
    # Post-turn side effects a real turn gets from the orchestrator, for the subset that
    # makes sense in an authored beat: the calendar actually moves and dice carry into
    # the next turn. Combat can't be driven from an inject — say so instead of claiming
    # it happened. (Chronicle/RAG and project ticks stay live-play-only by design.)
    if res.get("time_advance"):
        try:
            from backend.sim import calendar

            amount, unit = res["time_advance"]
            calendar.advance(amount, unit)
        except Exception as exc:  # noqa: BLE001
            display.append(f"⚠ time advance failed: {exc}")
    if res.get("combat_start") or res.get("combat_end"):
        display.append("note: combat tags do nothing in an injected beat — run fights in live play")
    if res.get("rolls"):
        orchestrator._save_pending(res["rolls"])
    display += [f"⚠ rejected: {r}" for r in res["rejected"]]
    display += [f"note: {n}" for n in res["notes"]]
    return display


@router.post("/play/inject")
async def play_inject(body: InjectBeat) -> dict:
    """Push a hand-authored DM beat (e.g. a montage) into the live feed. If `mechanics`
    are supplied they're applied through the deterministic boundary (no split-brain); the
    resulting real changes lead the `applied` display, with any free-text notes appended."""
    applied = list(body.applied)
    if body.mechanics:
        applied = apply_inject_mechanics(body.mechanics) + applied
    seq = await broker.inject(body.narrative, body.suggestions, applied)
    return {"ok": True, "seq": seq}


@router.post("/session/start")
async def session_start() -> dict:
    """Begin a session: warm the model, auto-backup, faction tick, then recap."""
    orchestrator.ensure_session()
    # warm the narration (and intimate) model up front so the first turn isn't cold
    _fire_warm(settings.narration_model)
    if settings.route_intimate and settings.intimate_model:
        _fire_warm(settings.intimate_model)
    try:
        backups.backup("session-start")
    except Exception as exc:  # noqa: BLE001
        logger.warning("session backup failed: %s", exc)
    moves = factions.tick()
    return {
        "previously": orchestrator.previously_on(),
        "faction_moves": moves,
        "warming": settings.narration_model,
    }


@router.post("/warmup")
async def warmup() -> dict:
    """Explicitly preload the narration model (UI can call this on page load)."""
    ok = await orchestrator.warm_model(settings.narration_model)
    if settings.route_intimate and settings.intimate_model:
        _fire_warm(settings.intimate_model)
    return {"model": settings.narration_model, "ok": ok}


@router.post("/session/end")
async def session_end() -> dict:
    """Close the session: generate a summary, flag open threads, back up."""
    summary = await orchestrator.end_session()
    try:
        backups.backup("session-end")
    except Exception as exc:  # noqa: BLE001
        logger.warning("session backup failed: %s", exc)
    return summary


@router.post("/session/undo")
def session_undo() -> dict:
    """Roll back to before the last turn (consumes one undo step)."""
    cur = broker.snapshot()
    if (cur and cur["status"] == "running"
            and time.time() - cur.get("started_at", 0) < broker.overall_timeout + 30):
        return {"ok": False, "detail": "a turn is still running — wait for it to finish"}
    result = backups.undo()
    if result is None:
        return {"ok": False, "detail": "nothing to undo"}
    orchestrator.clear_recent()
    # The DB rolled back, so the broker's in-memory feed must too — otherwise the undone
    # beat replays on the next reconnect and gets re-persisted by the next turn.
    broker.restore_feed()
    return {"ok": True, **result}


class BackupLabel(BaseModel):
    label: str = "manual"


@router.post("/session/backup")
def session_backup(body: BackupLabel) -> dict:
    path = backups.backup(body.label)
    return {"ok": True, "file": path.name}


@router.get("/session/backups")
def session_backups() -> dict:
    return backups.list_all()


@router.get("/session/export")
def session_export() -> FileResponse:
    path = backups.export_copy()
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)
