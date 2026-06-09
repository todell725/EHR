"""Companion-chat tests (storage + persona prompt; LLM call mocked)."""

import asyncio

from backend.core import state
from backend.dm import companion_chat


def test_history_persist_and_clear(fresh_db):
    companion_chat._save("PC-9", "user", "hey")
    companion_chat._save("PC-9", "assistant", "hey yourself")
    h = companion_chat.history("PC-9")
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert h[1]["content"] == "hey yourself"
    companion_chat.clear("PC-9")
    assert companion_chat.history("PC-9") == []


def test_system_prompt_uses_persona(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath", "is_player": 1})
    pc = {"id": "PC-2", "name": "Talmarr", "race": "Human", "class": "Ranger"}
    npc = {"name": "Talmarr", "pronouns": "she/her", "personality": ["wary", "loyal"],
           "want": "to be believed", "fear": "the forgetting void", "secret": "she saw it take someone",
           "disposition": {"PC-1": 15}}
    sp = companion_chat._system_prompt(pc, npc, "Kaelrath")
    assert "Talmarr" in sp and "she/her" in sp
    assert "wary, loyal" in sp
    assert "forgetting void" in sp
    assert "ONLY as Talmarr" in sp           # stays in character, no narrator


def test_send_stores_both_messages(monkeypatch, fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath", "is_player": 1})
    state.upsert_pc({"id": "PC-2", "name": "Talmarr", "is_player": 0, "race": "Human", "class": "Ranger"})

    class _Fake:
        async def chat(self, messages, **kw):
            return "  I'm here, Kaelrath.  "

    monkeypatch.setattr(companion_chat, "get_llm", lambda: _Fake())
    out = asyncio.run(companion_chat.send("PC-2", "you ok?"))
    assert out["reply"] == "I'm here, Kaelrath."
    assert "delta" in out  # relationship nudge present
    h = companion_chat.history("PC-2")
    assert h == [{"role": "user", "content": "you ok?"},
                 {"role": "assistant", "content": "I'm here, Kaelrath."}]


def test_chat_nudges_disposition(monkeypatch, fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath", "is_player": 1})
    state.upsert_pc({"id": "PC-2", "name": "Talmarr", "is_player": 0})
    state.upsert_npc({"id": "EH-9", "name": "Talmarr", "disposition": {"PC-1": 10}})

    class _Fake:
        def __init__(self): self.n = 0
        async def chat(self, messages, **kw):
            self.n += 1
            return "thank you, that means a lot" if self.n == 1 else "+2"  # reply, then judge

    fake = _Fake()  # one shared instance so the call counter persists across calls
    monkeypatch.setattr(companion_chat, "get_llm", lambda: fake)
    out = asyncio.run(companion_chat.send("PC-2", "I'm glad you're with us."))
    assert out["delta"] == 2
    assert out["disposition"] == 12          # 10 -> 12
    assert state.get_npc("EH-9")["disposition"]["PC-1"] == 12
