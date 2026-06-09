"""WebSocket transport test — drives the real /api/play/ws route with a mocked DM."""

from fastapi.testclient import TestClient

import backend.api.play as play
from backend.main import app


async def _fake_stream(action, pc_id=None):
    yield {"type": "start", "turn": 1}
    yield {"type": "token", "text": "You "}
    yield {"type": "token", "text": "see a wolf."}
    yield {"type": "result", "turn": 1, "narrative": "You see a wolf.",
           "suggestions": [], "applied": [], "rolls": []}


def _reset_broker():
    play.broker.current = None
    play.broker.recent.clear()
    play.broker.subscribers.clear()


def test_ws_turn_event_sequence(monkeypatch, fresh_db):
    _reset_broker()
    monkeypatch.setattr(play.orchestrator, "stream_turn", _fake_stream)
    with TestClient(app) as c:
        with c.websocket_connect("/api/play/ws") as ws:
            ws.send_json({"action": "look around"})
            events = []
            while True:
                ev = ws.receive_json()
                events.append(ev)
                if ev["type"] in ("result", "error"):
                    break
    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "token" in types
    assert types[-1] == "result"
    assert events[-1]["narrative"] == "You see a wolf."


def test_ws_rejects_empty_action(monkeypatch, fresh_db):
    _reset_broker()
    monkeypatch.setattr(play.orchestrator, "stream_turn", _fake_stream)
    with TestClient(app) as c:
        with c.websocket_connect("/api/play/ws") as ws:
            ws.send_json({"action": "   "})
            ev = ws.receive_json()
            assert ev["type"] == "error"
