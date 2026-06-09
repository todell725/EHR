"""Turn-broker tests — turns run detached from the socket and survive to persist."""

import asyncio

from backend.dm import broker as brokermod
from backend.dm import orchestrator


async def _fake_stream(action, pc_id=None):
    yield {"type": "start", "turn": 1}
    yield {"type": "token", "text": "You "}
    yield {"type": "token", "text": "kneel."}
    yield {"type": "result", "turn": 1, "narrative": "You kneel.",
           "suggestions": [], "applied": [], "rolls": []}


def test_broker_runs_persists_and_rejects_concurrent(monkeypatch, fresh_db):
    monkeypatch.setattr(orchestrator, "stream_turn", _fake_stream)
    tb = brokermod.TurnBroker()

    async def go():
        q = tb.subscribe()
        assert await tb.submit("kneel by the junction", None) is True
        assert await tb.submit("second action", None) is False  # one at a time
        events = []
        while True:
            ev = await asyncio.wait_for(q.get(), timeout=2)
            events.append(ev)
            if ev.get("type") == "turn_done":
                break
        return events

    events = asyncio.run(go())
    types = [e["type"] for e in events]
    assert "result" in types and types[-1] == "turn_done"
    assert all("seq" in e for e in events)              # every event is sequence-stamped
    last = brokermod.last_persisted()
    assert last and last["result"]["narrative"] == "You kneel."


def test_broker_replay_snapshot_survives_for_reconnect(monkeypatch, fresh_db):
    monkeypatch.setattr(orchestrator, "stream_turn", _fake_stream)
    tb = brokermod.TurnBroker()

    async def go():
        await tb.submit("kneel", None)
        # wait for completion without a live subscriber (simulates a disconnected client)
        for _ in range(50):
            if tb.snapshot() and tb.snapshot()["status"] == "done":
                break
            await asyncio.sleep(0.02)
        return tb.snapshot()

    snap = asyncio.run(go())
    assert snap["status"] == "done"                     # finished even with nobody listening
    assert any(e["type"] == "result" for e in snap["events"])  # replayable on reconnect
