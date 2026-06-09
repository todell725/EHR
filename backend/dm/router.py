"""NPC router — pick the NPCs most relevant to the current scene.

Lightweight successor to the origins "cognitive router": NPCs physically present
always qualify; beyond that we score alive NPCs by keyword overlap between the
player's action and each NPC's domains/role/name. Cheap, deterministic, and good
enough to keep the DM focused on the right cast without a second LLM call.
"""

from __future__ import annotations

import re

from backend.core import state

_WORD = re.compile(r"[a-z]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def select_npcs(action: str, *, location_id: str | None = None, limit: int = 4) -> list[dict]:
    present = state.list_npcs(location_id=location_id) if location_id else []
    present_ids = {n["id"] for n in present}

    action_tokens = _tokens(action)
    scored: list[tuple[float, dict]] = []
    for npc in state.list_npcs():  # alive, present-era
        if npc["id"] in present_ids:
            continue
        hay = _tokens(" ".join([
            npc.get("name", ""), npc.get("role", ""),
            " ".join(npc.get("domains") or []),
            npc.get("motivation", ""),
        ]))
        overlap = len(action_tokens & hay)
        if overlap:
            scored.append((overlap, npc))

    scored.sort(key=lambda s: s[0], reverse=True)
    extra = [npc for _, npc in scored[: max(0, limit - len(present))]]
    return (present + extra)[:limit]


def npc_brief(npc: dict) -> str:
    """One compact line of an NPC's drivers for the prompt's context block."""
    head = f"{npc['name']} ({npc.get('role','')})".strip()
    if npc.get("pronouns"):
        head += f" [{npc['pronouns']}]"
    bits = [head]
    if npc.get("personality"):
        bits.append("traits: " + ", ".join(npc["personality"][:4]))
    for label in ("want", "need", "fear", "secret"):
        if npc.get(label):
            bits.append(f"{label}: {npc[label]}")
    return " | ".join(bits)
