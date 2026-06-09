"""Hook endpoints — the investigation board.

A hook is a planted plot seed (Chekhov's gun). The dossier endpoint pulls everything
the campaign knows that's related to a thread and has the LLM synthesize "what's known
so far / what's uncertain / possible leads" — so clicking a hook explains it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.core import state
from backend.llm.client import get_llm
from backend.memory import rag

router = APIRouter(prefix="/api/hooks", tags=["hooks"])
logger = logging.getLogger("emberheart.api.hooks")


@router.get("")
def list_hooks() -> dict:
    return {"hooks": state.all_hooks()}


@router.get("/{hook_id}/dossier")
async def hook_dossier(hook_id: int) -> dict:
    hook = state.get_hook(hook_id)
    if not hook:
        raise HTTPException(404, "hook not found")

    desc = hook["description"]
    related = await rag.retrieve(desc, k=6, threshold=0.2)  # lower bar: gather leads

    synthesis = ""
    if related:
        notes = "\n".join(f"- ({r['kind']}) {r['text']}" for r in related)
        try:
            synthesis = await get_llm().chat(
                [
                    {"role": "system", "content":
                        "You are the campaign loremaster. Given an unresolved plot thread "
                        "and related notes from the chronicle, write 3-6 sentences: what is "
                        "KNOWN so far, what remains UNCERTAIN, and one or two possible leads. "
                        "Concrete and in-world; no invented facts beyond the notes."},
                    {"role": "user", "content": f"THREAD: {desc}\n\nRELATED NOTES:\n{notes}"},
                ],
                mode="adjudication",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("dossier synthesis failed: %s", exc)
            synthesis = "(could not synthesize — Ollama unavailable)"
    else:
        synthesis = "Nothing else is known about this thread yet — it's a fresh seed."

    return {"hook": hook, "synthesis": synthesis, "related": related}


@router.post("/{hook_id}/resolve")
def resolve(hook_id: int) -> dict:
    n = state.resolve_hook(str(hook_id))
    return {"ok": bool(n)}


@router.post("/consolidate")
async def consolidate() -> dict:
    """Cluster the open hooks into organized quests; retire the folded-in duplicates."""
    from backend.dm import threads

    return await threads.consolidate()
