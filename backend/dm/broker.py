"""Turn broker — runs a DM turn server-side, independent of any client socket.

The bug it fixes: turns used to be generated *inside* the WebSocket handler, so when a
phone backgrounded the app and the socket dropped, the generation was cancelled and the
result was lost. Here the turn runs as a detached asyncio task; sockets merely *subscribe*
to its event stream. Disconnect → the turn keeps going, finishes, and is persisted; the
next connection **replays** it so you never lose a beat.

Single-player model: one turn at a time. A submit while a turn is running is ignored.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque

from backend.core import db
from backend.core.config import settings
from backend.dm import orchestrator

logger = logging.getLogger("emberheart.broker")


class TurnBroker:
    def __init__(self) -> None:
        self.seq = 0
        self.current: dict | None = None          # the in-flight or last turn
        self.recent: deque[dict] = deque(maxlen=12)  # finished turns, replayed on (re)connect
        self.subscribers: set[asyncio.Queue] = set()

    @property
    def overall_timeout(self) -> float:
        """Hard ceiling on a single turn so a stalled stream can't wedge the broker."""
        return max(300.0, settings.cold_start_timeout + 120.0)

    # -------------------------------------------------------------- subscriptions
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    async def _broadcast(self, ev: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(ev)
            except Exception:  # noqa: BLE001 - a slow/closed subscriber must not break the turn
                pass

    # --------------------------------------------------------------------- running
    async def submit(self, action: str, pc_id: str | None) -> bool:
        """Start a turn. Returns False if one is genuinely still running."""
        cur = self.current
        if cur and cur["status"] == "running":
            elapsed = time.time() - cur.get("started_at", 0)
            if elapsed < self.overall_timeout + 30:
                return False
            # a turn stuck past its watchdog window is treated as dead — supersede it
            logger.warning("superseding a stale running turn (%.0fs old)", elapsed)
        self.seq += 1
        turn = {"seq": self.seq, "status": "running", "action": action,
                "pc_id": pc_id, "events": [], "started_at": time.time()}
        self.current = turn
        asyncio.create_task(self._run(turn))
        return True

    async def _run(self, turn: dict) -> None:
        seq = turn["seq"]

        async def emit(ev: dict) -> None:
            ev = {**ev, "seq": seq}
            turn["events"].append(ev)
            await self._broadcast(ev)

        async def consume() -> None:
            async for ev in orchestrator.stream_turn(turn["action"], turn["pc_id"]):
                await emit(ev)

        try:
            # hard watchdog: a mid-stream stall can't hang the turn forever
            await asyncio.wait_for(consume(), timeout=self.overall_timeout)
        except asyncio.TimeoutError:
            logger.error("turn %s timed out after %.0fs", seq, self.overall_timeout)
            await emit({"type": "error",
                        "message": "That turn stalled and was cancelled — try again."})
        except Exception as exc:  # noqa: BLE001
            logger.exception("turn %s failed", seq)
            await emit({"type": "error", "message": str(exc)})

        turn["status"] = "done"
        result = next((e for e in turn["events"] if e["type"] == "result"), None)
        _persist_last(turn["action"], result)
        self.recent.append(turn)
        self._persist_feed()
        await self._broadcast({"type": "turn_done", "seq": seq})

    # ---------------------------------------------------------------- injection
    async def inject(self, narrative: str, suggestions: list[dict] | None = None,
                     applied: list[str] | None = None) -> int:
        """Push a pre-authored DM beat into the feed as a finished turn (e.g. a hand-
        written montage). Appears live for connected clients and replays on reconnect.
        Does NOT run the model or apply mechanics — it's purely a narration beat."""
        # jump to a timestamp-based seq so the beat always renders, even for a client
        # whose lastSeq is stale from a prior (pre-restart) session
        self.seq = max(self.seq + 1, int(time.time()))
        seq = self.seq
        result = {
            "type": "result", "seq": seq, "turn": None, "narrative": narrative,
            "suggestions": suggestions or [], "applied": applied or [],
            "rejected": [], "notes": [], "rolls": [], "combat_start": False,
            "combat_end": False, "combat": None, "combat_log": [],
            "parse_notes": [], "model": "narration",
        }
        turn = {"seq": seq, "status": "done", "action": "(narration)", "pc_id": None,
                "events": [result], "started_at": time.time()}
        self.current = turn
        self.recent.append(turn)
        await self._broadcast(result)
        await self._broadcast({"type": "turn_done", "seq": seq})
        _persist_last(turn["action"], result)
        self._persist_feed()
        return seq

    # -------------------------------------------------------------------- recovery
    def snapshot(self) -> dict | None:
        return self.current

    def _persist_feed(self) -> None:
        """Save the replayable feed to disk so beats survive a server restart, not just
        an in-memory reconnect."""
        try:
            db.execute(
                "INSERT INTO meta (key, value) VALUES ('feed_recent', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [json.dumps(list(self.recent))],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not persist feed: %s", exc)

    def restore_feed(self) -> None:
        """Reload the feed from disk: at startup so the last beats (including injected
        montages) reappear after a restart, and after an undo so beats rolled back with
        the DB don't linger in memory and get replayed/re-persisted. The in-memory feed
        is reset first so this is authoritative either way; seq only ever ratchets up,
        so connected clients' dedup-by-seq stays valid."""
        self.recent = deque(maxlen=12)
        self.current = None
        try:
            row = db.query_one("SELECT value FROM meta WHERE key = 'feed_recent'")
            if not row:
                return
            turns = json.loads(row["value"])
            if not isinstance(turns, list) or not turns:
                return
            self.recent = deque(turns, maxlen=12)
            self.seq = max(self.seq, max(int(t.get("seq", 0)) for t in turns))
            self.current = turns[-1]
            logger.info("restored %d feed beats from disk", len(turns))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not restore feed: %s", exc)


def _persist_last(action: str, result: dict | None) -> None:
    try:
        db.execute(
            "INSERT INTO meta (key, value) VALUES ('last_turn', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [json.dumps({"action": action, "result": result})],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not persist last turn: %s", exc)


def last_persisted() -> dict | None:
    row = db.query_one("SELECT value FROM meta WHERE key = 'last_turn'")
    try:
        return json.loads(row["value"]) if row else None
    except Exception:  # noqa: BLE001
        return None


broker = TurnBroker()
