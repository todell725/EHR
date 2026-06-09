"""Entity endpoints — read NPCs/factions/quests, and create/update PCs.

Creating a player character applies homebrew defaults (HP from CON, AC from DEX) so
a new campaign is playable in one POST.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core import db, state
from backend.rules import homebrew, progression

router = APIRouter(prefix="/api", tags=["entities"])


def _sheet(pc: dict) -> dict:
    """Full computed character sheet: derived modifiers, proficiency, XP progress."""
    ab = pc.get("abilities") or {}
    lvl = pc.get("level", 1)
    prof = (pc.get("custom_dice") or {}).get("proficiency_bonus") or homebrew.proficiency_bonus(lvl)
    xp = pc.get("xp", 0)
    xp_table = homebrew.CHAR_LEVEL_XP
    xp_cur = xp_table[lvl] if lvl < len(xp_table) else xp
    xp_next = xp_table[lvl + 1] if lvl + 1 < len(xp_table) else None
    dex_mod = homebrew.ability_mod(ab.get("dex", 10))
    return {
        **pc,
        "modifiers": {k: homebrew.ability_mod(v) for k, v in ab.items()},
        "proficiency_bonus": prof,
        "initiative": (pc.get("custom_dice") or {}).get("initiative_bonus", dex_mod),
        "passive_perception": 10 + homebrew.ability_mod(ab.get("wis", 10)) + prof,
        "xp_current_level": xp_cur,
        "xp_next_level": xp_next,
        "xp_into_level": max(0, xp - xp_cur),
        "xp_needed": (xp_next - xp_cur) if xp_next else None,
        "levelup_available": progression.can_level_up(pc),
    }


@router.get("/pcs")
def list_pcs() -> list[dict]:
    return state.list_pcs()


class CreatePC(BaseModel):
    name: str
    race: str | None = None
    char_class: str | None = Field(default=None, alias="class")
    abilities: dict[str, int] = Field(
        default_factory=lambda: {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    )
    level: int = 1
    max_hp: int | None = None
    ac: int | None = None

    model_config = {"populate_by_name": True}


@router.post("/pcs")
def create_pc(body: CreatePC) -> dict:
    con_mod = homebrew.ability_mod(body.abilities.get("con", 10))
    dex_mod = homebrew.ability_mod(body.abilities.get("dex", 10))
    max_hp = body.max_hp if body.max_hp is not None else max(1, 8 + con_mod)
    ac = body.ac if body.ac is not None else 10 + dex_mod
    pc_id = "PC-" + uuid.uuid4().hex[:6]
    pc = {
        "id": pc_id, "name": body.name, "race": body.race, "class": body.char_class,
        "level": body.level, "xp": 0, "hp": max_hp, "max_hp": max_hp, "ac": ac,
        "abilities": body.abilities, "skills": {s: 1 for s in homebrew.IDLE_SKILLS},
        "custom_dice": {"proficiency_bonus": homebrew.proficiency_bonus(body.level)},
    }
    state.upsert_pc(pc)
    return state.get_pc(pc_id)


@router.get("/pcs/{pc_id}/sheet")
def pc_sheet(pc_id: str) -> dict:
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    return _sheet(pc)


@router.get("/pcs/{pc_id}/levelup")
def levelup_preview(pc_id: str) -> dict:
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    return {"eligible": progression.can_level_up(pc), **progression.preview(pc)}


class LevelUp(BaseModel):
    picks: dict = Field(default_factory=dict)
    force: bool = False  # GM override when XP isn't there yet


@router.post("/pcs/{pc_id}/levelup")
def levelup_apply(pc_id: str, body: LevelUp) -> dict:
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    if not progression.can_level_up(pc) and not body.force:
        raise HTTPException(400, "not enough XP to level up (use force for GM override)")
    if pc.get("level", 1) >= 20:
        raise HTTPException(400, "already at max level")
    result = progression.apply(pc, body.picks)
    state.upsert_pc(result["patch"])
    return {"log": result["log"], "sheet": _sheet(state.get_pc(pc_id))}


class SeedFeatures(BaseModel):
    overwrite: bool = False


@router.post("/pcs/{pc_id}/seed-features")
def seed_features(pc_id: str, body: SeedFeatures) -> dict:
    """Backfill the auto class features for a PC's current level (fresh sheets)."""
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    if pc.get("features") and not body.overwrite:
        return {"sheet": _sheet(pc), "note": "already has features"}
    state.upsert_pc({"id": pc_id, "features": progression.seed_starting_features(pc)})
    return {"sheet": _sheet(state.get_pc(pc_id))}


# words that leak into inventory via bugs but are not real items
_JUNK_ITEMS = {"exhaustion", "minor gas strain", "none", "blinded", "dead", "poisoned"}


class InvSet(BaseModel):
    item: str
    qty: int = 0      # 0 drops the stack


@router.post("/pcs/{pc_id}/inventory/set")
def inventory_set(pc_id: str, body: InvSet) -> dict:
    """Set a stack's quantity (0 removes it) — the drop/adjust control for the pack."""
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    target = body.item.strip().lower()
    inv = []
    for it in pc.get("inventory") or []:
        if it.get("item", "").strip().lower() == target:
            if body.qty > 0:
                inv.append({**it, "qty": body.qty})
            # else: drop it
        else:
            inv.append(it)
    state.upsert_pc({"id": pc_id, "inventory": inv})
    return {"sheet": _sheet(state.get_pc(pc_id))}


@router.post("/pcs/{pc_id}/inventory/tidy")
def inventory_tidy(pc_id: str) -> dict:
    """Merge duplicate stacks (case-insensitive) and strip junk non-items."""
    pc = state.get_pc(pc_id)
    if not pc:
        raise HTTPException(404, "pc not found")
    merged: dict[str, dict] = {}
    for it in pc.get("inventory") or []:
        name = (it.get("item") or "").strip()
        if not name or name.lower() in _JUNK_ITEMS:
            continue
        key = name.lower()
        if key in merged:
            merged[key]["qty"] = merged[key].get("qty", 1) + it.get("qty", 1)
        else:
            merged[key] = {"item": name, "qty": it.get("qty", 1)}
    state.upsert_pc({"id": pc_id, "inventory": list(merged.values())})
    return {"sheet": _sheet(state.get_pc(pc_id))}


@router.post("/npcs/{npc_id}/promote")
def promote_npc(npc_id: str) -> dict:
    """Turn an NPC into a DM-controlled party companion (a managed sheet)."""
    pc = state.promote_npc_to_party(npc_id)
    if not pc:
        raise HTTPException(404, "npc not found")
    return {"companion": _sheet(pc)}


@router.get("/npcs")
def list_npcs(era: str = "present") -> list[dict]:
    return state.all_npcs(era=era)


@router.get("/npcs/{npc_id}")
def get_npc(npc_id: str) -> dict:
    npc = state.get_npc(npc_id)
    if not npc:
        raise HTTPException(404, "npc not found")
    return npc


@router.get("/factions")
def list_factions() -> list[dict]:
    return state.list_factions()


@router.get("/quests")
def list_quests(status: str | None = None) -> list[dict]:
    return state.list_quests(status)


@router.get("/locations")
def list_locations() -> list[dict]:
    rows = db.query("SELECT * FROM locations ORDER BY name")
    return [db.row_to_dict(r, ("features",)) for r in rows]
