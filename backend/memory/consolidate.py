"""Memory consolidation.

Every N turns we compress the recent play into a single dense chronicle summary and
push it into the semantic store. This keeps long campaigns retrievable without
relying on a rolling chat log (which forgets early facts after ~20 turns).
"""

from __future__ import annotations

import logging

from backend.core import state
from backend.core.config import settings
from backend.llm.client import get_llm
from backend.memory import rag

logger = logging.getLogger("emberheart.consolidate")

_SYSTEM = (
    "You are the campaign archivist. Compress the recent events into a dense, "
    "factual chronicle summary of 4-8 sentences. Preserve names, decisions, "
    "consequences, and any unresolved threads. No flourish, no second person."
)


def should_consolidate(turn_counter: int) -> bool:
    every = max(1, settings.consolidate_every_turns)
    return turn_counter > 0 and turn_counter % every == 0


async def consolidate_recent(window: int = 12) -> int | None:
    """Summarize recent chronicle beats into one stored memory chunk."""
    beats = state.recent_chronicle(limit=window)
    if not beats:
        return None
    joined = "\n".join(f"- {b['content']}" for b in beats)
    try:
        summary = await get_llm().chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Recent events:\n{joined}"},
            ],
            mode="adjudication",  # cold temp: we want faithful compression, not invention
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("consolidation LLM call failed: %s", exc)
        return None
    if not summary.strip():
        return None
    return await rag.store(summary.strip(), kind="session", source="consolidation")
