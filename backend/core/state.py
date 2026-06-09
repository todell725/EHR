"""Typed accessors over the structured-state tables.

This is the *only* module the orchestrator and sim use to read/write game state,
so the rule "the LLM never mutates state directly" is enforced structurally: the
LLM produces `[MECHANICS]` directives, the mechanics layer calls functions here.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from backend.core import db
from backend.rules import homebrew, progression

# JSON-typed columns per table, for decoding on read.
_NPC_JSON = ("domains", "personality", "disposition")
_PC_JSON = ("abilities", "conditions", "inventory", "skills", "custom_dice", "features", "skill_xp")
_FACTION_JSON = ("goals", "leaders", "relationships", "reputation", "threat_list")
_WORLD_JSON = ("global_events",)


# --------------------------------------------------------------------- world
def get_world() -> dict:
    row = db.query_one("SELECT * FROM world_state WHERE id = 1")
    return db.row_to_dict(row, _WORLD_JSON) or {}


def update_world(**fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = time.time()
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(
        f"UPDATE world_state SET {sets} WHERE id = 1",
        [db.dumps(v) if isinstance(v, (list, dict)) else v for v in fields.values()],
    )


def bump_turn() -> int:
    db.execute("UPDATE world_state SET turn_counter = turn_counter + 1 WHERE id = 1")
    return get_world().get("turn_counter", 0)


# ----------------------------------------------------------- player characters
def list_pcs() -> list[dict]:
    """All party-roster characters — heroes AND DM-controlled companions."""
    rows = db.query("SELECT * FROM player_characters ORDER BY is_player DESC, id")
    return [db.row_to_dict(r, _PC_JSON) for r in rows]


def heroes() -> list[dict]:
    return [p for p in list_pcs() if p.get("is_player", 1)]


def companions() -> list[dict]:
    return [p for p in list_pcs() if not p.get("is_player", 1)]


def _infer_class(role: str | None) -> str:
    r = (role or "").lower()
    if any(w in r for w in ("scout", "ranger", "hunt", "track", "archer")):
        return "Ranger"
    if any(w in r for w in ("mage", "wizard", "arcan", "sorcer", "witch")):
        return "Wizard"
    if any(w in r for w in ("priest", "cleric", "healer", "acolyte")):
        return "Cleric"
    if any(w in r for w in ("rogue", "thief", "assassin", "blade", "spy")):
        return "Rogue"
    if any(w in r for w in ("knight", "guard", "soldier", "warrior", "captain")):
        return "Fighter"
    return "Fighter"


def promote_npc_to_party(npc_id: str) -> dict | None:
    """Turn an NPC into a DM-controlled party companion: a full character sheet
    (is_player=0) you manage, but the DM voices and acts. Keeps the NPC record for
    history but pulls it from the active roster (status='party')."""
    npc = get_npc(npc_id)
    if npc is None:
        return None
    cls = _infer_class(npc.get("role"))
    abilities = {"str": 12, "dex": 13, "con": 13, "int": 10, "wis": 12, "cha": 11}
    con_mod = homebrew.ability_mod(abilities["con"])
    dex_mod = homebrew.ability_mod(abilities["dex"])
    hp = max(1, 8 + con_mod)
    pcid = "PC-" + uuid.uuid4().hex[:6]
    pronoun = (npc.get("pronouns") or "").strip()
    note = " · ".join(x for x in [pronoun, "DM-controlled companion", npc.get("bio", "")] if x)
    pc = {
        "id": pcid, "name": npc["name"], "race": npc.get("race"), "class": cls,
        "level": 1, "xp": 0, "hp": hp, "max_hp": hp, "ac": 12 + dex_mod,
        "abilities": abilities, "is_player": 0, "notes": note[:300],
        "skills": {s: 1 for s in homebrew.IDLE_SKILLS},
        "custom_dice": {"proficiency_bonus": homebrew.proficiency_bonus(1)},
        "features": progression.seed_starting_features({"class": cls, "level": 1}),
        "status": "alive",
    }
    upsert_pc(pc)
    set_npc_status(npc_id, "party")  # leave the active NPC roster
    return get_pc(pcid)


def get_pc(pc_id: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM player_characters WHERE id = ?", [pc_id]), _PC_JSON
    )


def upsert_pc(pc: dict) -> None:
    db.upsert("player_characters", pc)


def grant_skill_xp(pc_id: str, skill: str, amount: int) -> dict | None:
    """Add XP to an idle skill (smithing/hunting/...) and recompute its level via the
    RuneScape-style curve. Backfills XP from the current level the first time."""
    pc = get_pc(pc_id)
    if pc is None:
        return None
    skill = (skill or "").strip().lower()
    if not skill:
        return None
    sx = dict(pc.get("skill_xp") or {})
    skills = dict(pc.get("skills") or {})
    cur_level = int(skills.get(skill, 1))
    base = int(sx.get(skill, homebrew.skill_xp_for_level(cur_level)))
    sx[skill] = base + max(0, int(amount))
    new_level = homebrew.skill_level_for_xp(sx[skill])
    skills[skill] = new_level
    upsert_pc({"id": pc_id, "skill_xp": sx, "skills": skills})
    return {"skill": skill, "xp": sx[skill], "level": new_level, "leveled": new_level > cur_level}


# -------------------------------------------------------------------------- npcs
def get_npc(npc_id: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM npcs WHERE id = ?", [npc_id]), _NPC_JSON
    )


def find_npc_by_name(name: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM npcs WHERE name = ? COLLATE NOCASE", [name]),
        _NPC_JSON,
    )


def list_npcs(
    *, location_id: str | None = None, status: str = "alive", era: str = "present"
) -> list[dict]:
    sql = "SELECT * FROM npcs WHERE era = ?"
    params: list[Any] = [era]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if location_id:
        sql += " AND location_id = ?"
        params.append(location_id)
    return [db.row_to_dict(r, _NPC_JSON) for r in db.query(sql, params)]


def all_npcs(era: str | None = None) -> list[dict]:
    if era:
        rows = db.query("SELECT * FROM npcs WHERE era = ?", [era])
    else:
        rows = db.query("SELECT * FROM npcs")
    return [db.row_to_dict(r, _NPC_JSON) for r in rows]


def upsert_npc(npc: dict) -> None:
    db.upsert("npcs", npc)


def set_npc_disposition(npc_id: str, pc_id: str, delta: int) -> int | None:
    npc = get_npc(npc_id)
    if npc is None:
        return None
    disp = npc.get("disposition") or {}
    disp[pc_id] = int(disp.get(pc_id, 0)) + delta
    db.execute("UPDATE npcs SET disposition = ? WHERE id = ?", [db.dumps(disp), npc_id])
    return disp[pc_id]


def set_npc_status(npc_id: str, status: str) -> None:
    db.execute("UPDATE npcs SET status = ? WHERE id = ?", [status, npc_id])


# ---------------------------------------------------------------------- factions
def list_factions() -> list[dict]:
    return [
        db.row_to_dict(r, _FACTION_JSON)
        for r in db.query("SELECT * FROM factions ORDER BY name")
    ]


def get_faction(fid: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM factions WHERE id = ?", [fid]), _FACTION_JSON
    )


def upsert_faction(f: dict) -> None:
    db.upsert("factions", f)


def change_faction_rep(fid: str, pc_id: str, delta: int) -> int | None:
    f = get_faction(fid)
    if f is None:
        # tolerate name-based reference by matching name
        row = db.query_one("SELECT * FROM factions WHERE name = ? COLLATE NOCASE", [fid])
        if row is None:
            return None
        f = db.row_to_dict(row, _FACTION_JSON)
        fid = f["id"]
    rep = f.get("reputation") or {}
    rep[pc_id] = max(-100, min(100, int(rep.get(pc_id, 0)) + delta))
    db.execute("UPDATE factions SET reputation = ? WHERE id = ?", [db.dumps(rep), fid])
    return rep[pc_id]


# ---------------------------------------------------------------------- quests
def list_quests(status: str | None = None) -> list[dict]:
    if status:
        rows = db.query("SELECT * FROM quests WHERE status = ?", [status])
    else:
        rows = db.query("SELECT * FROM quests")
    return [db.row_to_dict(r, ("objectives", "rewards")) for r in rows]


def upsert_quest(q: dict) -> None:
    db.upsert("quests", q)


# ---------------------------------------------------------------------- journal
def add_journal(title: str, body: str, *, mood: str = "", in_world_date: str = "",
                author: str = "Kaelrath") -> int:
    cur = db.execute(
        "INSERT INTO journal (title, body, mood, in_world_date, author) VALUES (?,?,?,?,?)",
        [title, body, mood, in_world_date, author],
    )
    return cur.lastrowid


def list_journal() -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM journal ORDER BY id DESC")]


def delete_journal(entry_id: int) -> bool:
    return db.execute("DELETE FROM journal WHERE id = ?", [entry_id]).rowcount > 0


# -------------------------------------------------------------------- mounts
_MOUNT_JSON = ("traits",)


def list_mounts(owner_pc_id: str | None = None, *, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM mounts WHERE status != 'dead'"
    params: list[Any] = []
    if owner_pc_id:
        sql += " AND owner_pc_id = ?"
        params.append(owner_pc_id)
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY name"
    return [db.row_to_dict(r, _MOUNT_JSON) for r in db.query(sql, params)]


def get_mount(mount_id: str) -> dict | None:
    return db.row_to_dict(db.query_one("SELECT * FROM mounts WHERE id = ?", [mount_id]), _MOUNT_JSON)


def find_mount_by_name(name: str) -> dict | None:
    row = db.query_one("SELECT * FROM mounts WHERE LOWER(name) = LOWER(?)", [(name or "").strip()])
    return db.row_to_dict(row, _MOUNT_JSON) if row else None


def upsert_mount(mount: dict) -> None:
    db.upsert("mounts", mount)


# ----------------------------------------------------- idle/camp materials (stores)
# Canonical material keys match the idle ACTIVITIES; this maps the words the DM (and my
# montages) actually use onto them, so the larder and the narrative speak one language.
_MATERIAL_ALIASES = {
    "log": "wood", "logs": "wood", "lumber": "wood", "timber": "wood", "firewood": "wood",
    "meat": "raw_meat", "raw meat": "raw_meat", "game": "raw_meat",
    "fish": "raw_fish", "raw fish": "raw_fish",
    "fiber": "plant_fiber", "fibre": "plant_fiber", "plant fiber": "plant_fiber",
    "pelt": "hide", "pelts": "hide", "hides": "hide", "skin": "hide",
    "herb": "herbs", "berry": "berries",
    "ores": "ore", "rock": "stone", "stones": "stone", "rocks": "stone",
    "bar": "metal_bar", "bars": "metal_bar", "ingot": "metal_bar", "metal bar": "metal_bar",
    "meal": "cooked_meal", "meals": "cooked_meal", "food": "cooked_meal", "cooked meal": "cooked_meal",
    "leathers": "leather",
}


def normalize_material(name: str) -> str:
    key = (name or "").strip().lower()
    key = _MATERIAL_ALIASES.get(key, key)
    return key.replace(" ", "_")


def get_materials() -> dict:
    row = db.query_one("SELECT value FROM meta WHERE key = 'idle_materials'")
    return json.loads(row["value"]) if row else {}


def set_materials(mats: dict) -> None:
    db.execute("INSERT INTO meta (key, value) VALUES ('idle_materials', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", [json.dumps(mats)])


# All material read-modify-writes serialize on this lock. The idle tick, deposits,
# invests, and the DM's MATERIAL_SPEND/GAIN all mutate the same `idle_materials` blob
# from different threads (the async idle loop vs threadpool request handlers); without
# this, a slow read-modify-write would clobber a concurrent removal and "restore" it.
MATERIAL_LOCK = threading.RLock()


def adjust_material(name: str, delta: int) -> int:
    """Add (or remove, if delta<0) a material in the shared camp stores. Clamps at 0,
    drops empties. Returns the new quantity. Normalizes the name first."""
    key = normalize_material(name)
    with MATERIAL_LOCK:
        mats = get_materials()
        new = max(0, int(mats.get(key, 0)) + int(delta))
        if new == 0:
            mats.pop(key, None)
        else:
            mats[key] = new
        set_materials(mats)
        return new


# ------------------------------------------------------------------ world hooks
def add_hook(description: str, payoff_hint: str = "", turn: int = 0) -> int:
    cur = db.execute(
        "INSERT INTO world_hooks (description, payoff_hint, planted_turn) VALUES (?,?,?)",
        [description, payoff_hint, turn],
    )
    return cur.lastrowid


def open_hooks(limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM world_hooks WHERE status != 'resolved' ORDER BY id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [db.row_to_dict(r, ("related",)) for r in db.query(sql)]


def all_hooks() -> list[dict]:
    return [
        db.row_to_dict(r, ("related",))
        for r in db.query("SELECT * FROM world_hooks ORDER BY id DESC")
    ]


def get_hook(hook_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM world_hooks WHERE id = ?", [hook_id]), ("related",)
    )


def resolve_hook(ref: str) -> int:
    """Mark a hook resolved by id, or by a fragment of its description. Returns count."""
    ref = (ref or "").strip()
    if not ref:
        return 0
    if ref.isdigit():
        cur = db.execute(
            "UPDATE world_hooks SET status = 'resolved' WHERE id = ? AND status != 'resolved'",
            [int(ref)],
        )
    else:
        cur = db.execute(
            "UPDATE world_hooks SET status = 'resolved' "
            "WHERE status != 'resolved' AND description LIKE ?",
            [f"%{ref[:40]}%"],
        )
    return cur.rowcount


# ------------------------------------------------------------------- chronicle
def add_chronicle(
    content: str,
    *,
    in_world_date: str = "",
    tags: list[str] | None = None,
    npcs: list[str] | None = None,
    significant: bool = True,
    session_id: int | None = None,
) -> int:
    cur = db.execute(
        "INSERT INTO chronicle (content, in_world_date, tags, npcs_involved, significant, session_id) "
        "VALUES (?,?,?,?,?,?)",
        [
            content,
            in_world_date,
            db.dumps(tags or []),
            db.dumps(npcs or []),
            1 if significant else 0,
            session_id,
        ],
    )
    return cur.lastrowid


def recent_chronicle(limit: int = 8, tags: list[str] | None = None) -> list[dict]:
    if tags:
        # SQLite JSON array containment via LIKE is fuzzy but sufficient for our tag set
        clauses = " OR ".join(["tags LIKE ?"] * len(tags))
        params = [f'%"{t}"%' for t in tags] + [limit]
        rows = db.query(f"SELECT * FROM chronicle WHERE {clauses} ORDER BY id DESC LIMIT ?", params)
    else:
        rows = db.query("SELECT * FROM chronicle ORDER BY id DESC LIMIT ?", [limit])
    return [db.row_to_dict(r, ("tags", "npcs_involved")) for r in reversed(rows)]

def chronicle_count() -> int:
    """Return total number of chronicle entries."""
    row = db.query_one("SELECT COUNT(*) AS c FROM chronicle")
    return row["c"] if row else 0