"""Faction simulation — the world's other players.

Factions are first-class agents with a goal tier (survival -> consolidation ->
expansion -> dominance) and a resource score. At session start a lightweight tick
lets each faction make one move appropriate to its tier and means. Moves nudge
resources/relationships and surface as narratable chronicle beats the DM can weave
into the "Previously on" recap.
"""

from __future__ import annotations

import random

from backend.core import state

GOAL_TIERS = ["survival", "consolidation", "expansion", "dominance"]
RES_MIN, RES_MAX = 0, 40   # resources are bounded so drift can't compound to runaway dominance

# Candidate moves per tier; one is chosen each tick (gated by resources).
_MOVES = {
    "survival": ["fortifies its holdings", "scrounges for supplies", "recruits desperate hands"],
    "consolidation": ["consolidates territory", "forges a local alliance", "roots out dissent"],
    "expansion": ["expands toward new ground", "raids a rival's caravan", "courts a neighbor"],
    "dominance": ["moves to dominate a rival", "sends an assassin", "demands tribute"],
}


def _maybe_advance_tier(f: dict) -> str:
    """Resource thresholds gently push a faction up the goal ladder."""
    tier = f.get("goal_tier", "survival")
    res = f.get("resources", 10)
    idx = GOAL_TIERS.index(tier) if tier in GOAL_TIERS else 0
    if res >= 30 and idx < 3:
        idx += 1
    elif res < 5 and idx > 0:
        idx -= 1
    return GOAL_TIERS[idx]


def tick() -> list[dict]:
    """Advance every faction one move. Returns [{faction, move, tier}]."""
    moves: list[dict] = []
    for f in state.list_factions():
        tier = _maybe_advance_tier(f)
        move = random.choice(_MOVES.get(tier, _MOVES["survival"]))
        # resource drift, zero-mean with mild reversion off the rails so factions don't all
        # balloon to dominance (rich → action costs bite) or death-spiral to 0 (poor → claw back)
        res = f.get("resources", 10)
        delta = random.randint(-3, 3)
        if res > 30:
            delta -= 1
        elif res < 8:
            delta += 1
        new_res = max(RES_MIN, min(RES_MAX, res + delta))
        state.upsert_faction({"id": f["id"], "goal_tier": tier, "resources": new_res})

        text = f"{f['name']} {move}."
        state.add_chronicle(text, tags=["faction", f["id"]], significant=False)
        moves.append({"faction": f["name"], "move": move, "tier": tier})
    return moves
