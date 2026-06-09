import asyncio
import json

from backend.core import state
from backend.dm import threads


def test_consolidate_clusters_hooks_into_quests(monkeypatch, fresh_db):
    # distinct wording so the cheap dedup keeps them and the clustering path runs
    ids = [state.add_hook(d) for d in [
        "the northern nexus pulses with ley energy",
        "moonveil herb grows only deep in the frostfen marsh",
        "an iron vault door demands a blood seal to open",
        "Lyara's shade guards the spiral stair below",
        "Bheric the smith carries forty years of buried guilt",
        "the tuned chime resonates against the buried crystal heart",
    ]]

    class _Fake:
        async def chat(self, messages, **kw):
            return json.dumps({"quests": [
                {"title": "The Vault Mystery", "description": "What sleeps below.", "hook_ids": ids[:4]},
                {"title": "Resolved / Past", "description": "done", "hook_ids": ids[4:]},
            ]})

    monkeypatch.setattr(threads, "get_llm", lambda: _Fake())
    r = asyncio.run(threads.consolidate())

    assert r["quests_created"] == 1          # the 'Resolved / Past' cluster makes no quest
    assert r["hooks_retired"] == 6           # every hook folded in
    assert r["remaining_hooks"] == 0
    assert any(q["title"] == "The Vault Mystery" for q in state.list_quests())


def test_consolidate_noop_when_few_hooks(fresh_db):
    state.add_hook("lonely thread")
    r = asyncio.run(threads.consolidate())
    assert r["quests_created"] == 0
