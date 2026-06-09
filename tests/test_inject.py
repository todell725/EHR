import asyncio

from backend.dm.broker import TurnBroker


def test_inject_emits_result_and_persists(fresh_db):
    broker = TurnBroker()
    q = broker.subscribe()

    seq = asyncio.run(broker.inject(
        "A montage of the long road north.",
        suggestions=[{"text": "Press on", "requires_roll": False}],
        applied=["Kaelrath +1200 XP"],
    ))

    assert seq > 0
    # the finished turn is the current snapshot (so a reconnect replays it)
    snap = broker.snapshot()
    assert snap and snap["status"] == "done" and snap["seq"] == seq
    # a result event was broadcast to subscribers
    ev = q.get_nowait()
    assert ev["type"] == "result" and ev["narrative"].startswith("A montage")
    assert ev["applied"] == ["Kaelrath +1200 XP"]
