"""Thread consolidation — cluster a sprawl of open hooks into organized quests.

The DM seeds hooks faster than it resolves them, so over a long campaign the Threads panel
becomes a flat wall of near-duplicates. This reads every open hook, has the model cluster
them into a handful of coherent QUESTS (merging the redundant ones), creates those quests,
and retires the raw hooks that were folded in — leaving a readable quest log instead of
158 loose strands.
"""

from __future__ import annotations

import json
import logging
import uuid

from backend.core import state
from backend.core.config import settings
from backend.llm.client import get_llm

logger = logging.getLogger("emberheart.threads")

_SYSTEM = (
    "You organize a fantasy campaign's tangled plot threads. Cluster the numbered threads "
    "below into 5-12 coherent QUESTS, merging duplicates and closely-related threads. For "
    "each quest give: a short evocative title, a 1-3 sentence consolidated description of the "
    "live questions and stakes, and the list of thread ids it covers. Every id should fall "
    "under exactly one quest; drop nothing. Resolved or clearly past threads may be grouped "
    "into a quest titled 'Resolved / Past'. Return ONLY JSON: "
    '{"quests":[{"title":"...","description":"...","hook_ids":[1,2,3]}]}'
)


def _dedupe_open_hooks() -> int:
    """Cheap, no-LLM pass: retire near-identical hooks (the DM re-seeds the same thread
    over and over). Keeps the first of each cluster. Returns how many were retired."""
    kept: list[set] = []
    retired = 0
    for h in state.open_hooks():
        toks = set(h["description"].lower().split())
        if not toks:
            continue
        if any(len(toks & k) / max(1, len(toks)) > 0.6 for k in kept):
            if state.resolve_hook(str(h["id"])):
                retired += 1
        else:
            kept.append(toks)
    return retired


async def consolidate() -> dict:
    # 1) collapse the obvious duplicates first — this alone clears most of the clutter
    deduped = _dedupe_open_hooks()
    hooks = state.open_hooks()
    if len(hooks) < 4:
        return {"quests_created": 0, "hooks_retired": deduped,
                "remaining_hooks": len(hooks), "quests": []}

    # 2) cluster the survivors into quests on the FAST local model (won't time out)
    listing = "\n".join(f"[{h['id']}] {h['description']}" for h in hooks)
    try:
        raw = await get_llm().chat(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": listing}],
            model=settings.chat_model, response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("consolidate LLM call failed: %s", exc)
        return {"error": str(exc), "quests_created": 0, "hooks_retired": deduped,
                "remaining_hooks": len(state.open_hooks())}

    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:  # noqa: BLE001
        return {"note": "deduped only (clustering output unparseable)", "quests_created": 0,
                "hooks_retired": deduped, "remaining_hooks": len(state.open_hooks())}

    valid = {h["id"] for h in hooks}
    created, retired = 0, 0
    new_quests = []
    for q in data.get("quests", []):
        title = (q.get("title") or "").strip()
        if not title:
            continue
        ids = [int(i) for i in q.get("hook_ids", [])
               if str(i).isdigit() and int(i) in valid]
        # 'Resolved/Past' clusters just retire their hooks without making an active quest
        is_resolved = "resolv" in title.lower() or "past" in title.lower()
        if not is_resolved:
            qid = "Q-" + uuid.uuid4().hex[:8]
            state.upsert_quest({"id": qid, "title": title[:120],
                                "description": (q.get("description") or "")[:600],
                                "status": "active"})
            created += 1
            new_quests.append(title)
        for hid in ids:
            if state.resolve_hook(str(hid)):
                retired += 1

    return {"quests_created": created, "hooks_retired": deduped + retired,
            "remaining_hooks": len(state.open_hooks()), "quests": new_quests}
