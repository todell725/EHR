"""The replayable feed must survive a server restart (not just an in-memory reconnect)."""
import asyncio

from backend.dm.broker import TurnBroker


def test_feed_survives_restart(fresh_db):
    b = TurnBroker()
    asyncio.run(b.inject("A hand-authored montage beat", suggestions=[{"text": "go"}],
                         applied=["something happened"]))
    assert len(b.recent) == 1

    # simulate a restart: a brand-new broker starts with an empty buffer…
    b2 = TurnBroker()
    assert len(b2.recent) == 0
    # …until it restores from disk
    b2.restore_feed()
    assert len(b2.recent) == 1
    result = b2.recent[-1]["events"][0]
    assert result["narrative"] == "A hand-authored montage beat"
    assert b2.seq >= b.seq            # seq high-water mark preserved (no replayed-as-old beats)
