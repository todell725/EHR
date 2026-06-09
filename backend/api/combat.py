"""Combat endpoints — start an encounter, auto-resolve to the player's turn, end it."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.sim import combat

router = APIRouter(prefix="/api/combat", tags=["combat"])


class Enemy(BaseModel):
    name: str
    hp: int = 10
    ac: int = 12
    attack_bonus: int = 3
    damage: str = "1d6+1"
    ai: str = "berserker"  # berserker | tactical | cowardly | spellcaster


class StartCombat(BaseModel):
    enemies: list[Enemy]


@router.get("")
def status() -> dict:
    return {"encounter": combat.status()}


@router.post("/start")
def start(body: StartCombat) -> dict:
    enc = combat.start_combat([e.model_dump() for e in body.enemies])
    # immediately resolve any enemies that act before the first player
    resolved = combat.advance_to_player()
    return {"encounter": combat.status(), "opening": resolved.get("log", [])}


@router.post("/advance")
def advance() -> dict:
    """Call after the player's action has been adjudicated (DM emits ENEMY_HP etc.)."""
    return combat.end_player_turn()


@router.post("/end")
def end() -> dict:
    combat.end_combat()
    return {"ended": True}
