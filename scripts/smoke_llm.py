"""Manual smoke test for the Ollama connection (requires a running Ollama).

    python scripts/smoke_llm.py
"""

import asyncio

from backend.llm.client import get_llm


async def main() -> None:
    llm = get_llm()
    print("health:", await llm.health_check())
    print("models:", await llm.list_models())
    vec = await llm.embed("a cold ember on a dark frontier")
    print("embedding dims:", len(vec))
    reply = await llm.chat(
        [{"role": "user", "content": "In one sentence, set a grim fantasy scene."}],
        mode="narration",
    )
    print("chat:", reply)
    await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
