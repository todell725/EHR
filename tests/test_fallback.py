"""Latency-fallback tests for the narration helper (mocked LLM, no Ollama)."""

import asyncio

from backend.dm import orchestrator


class _FakeLLM:
    def __init__(self, primary_slow: bool):
        self.primary_slow = primary_slow

    def stream_chat(self, messages, mode=None, model=None):
        slow, primary_slow = self.primary_slow, self.primary_slow

        async def primary():
            if slow:
                await asyncio.sleep(0.3)  # exceeds the tiny ttft -> triggers fallback
            yield "PRIMARY"

        async def fallback():
            for t in ("Hello ", "world"):
                yield t

        return primary() if model == "cloud" else fallback()


def _run(fake):
    async def collect():
        out = []
        async for ev in orchestrator._narrate([], "cloud", "local", ttft=0.05):
            out.append(ev)
        return out

    return asyncio.run(collect())


def test_falls_back_when_primary_stalls(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_llm", lambda: _FakeLLM(primary_slow=True))
    out = _run(None)
    assert ("fallback", "local") in out
    assert ("delta", "Hello ") in out
    assert ("delta", "PRIMARY") not in out  # primary was abandoned


def test_uses_primary_when_fast(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_llm", lambda: _FakeLLM(primary_slow=False))
    out = _run(None)
    assert ("fallback", "local") not in out
    assert ("delta", "PRIMARY") in out


def test_cold_start_grace_then_warm(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "narration_timeout", 75.0)
    monkeypatch.setattr(orchestrator.settings, "cold_start_timeout", 180.0)
    orchestrator._warmed.discard("cloud")
    # cold: unknown model gets the big grace budget
    assert orchestrator._timeout_for("cloud") == 180.0
    # once warmed, it drops to the snappy budget
    orchestrator.mark_warm("cloud")
    assert orchestrator._timeout_for("cloud") == 75.0
    orchestrator._warmed.discard("cloud")
