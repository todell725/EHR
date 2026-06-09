"""Combat engine — deterministic, Python-owned tactical resolution.

The DM narrates; this module adjudicates. Initiative, hit/damage rolls, enemy AI,
zone positioning, and death saves all resolve here so results can't be biased by the
LLM. The orchestrator hands the DM the combat log to dramatize.

At most one encounter is `active` at a time (enforced by convention + `end_combat`).
Zones are abstract (Engaged / Close / Far / Out) rather than a grid — enough for the
AI to act coherently without a battle map.
"""

from __future__ import annotations

import json
import random

from backend.core import db, state
from backend.rules import dice, homebrew

ZONES = ["Engaged", "Close", "Far", "Out"]
ENEMY_DEFAULTS = {"hp": 10, "ac": 12, "attack_bonus": 3, "damage": "1d6+1",
                  "ai": "berserker", "zone": "Close"}


# --------------------------------------------------------------- persistence
def _active_row():
    return db.query_one("SELECT * FROM combat_encounters WHERE status = 'active' ORDER BY id DESC LIMIT 1")


def status() -> dict | None:
    row = _active_row()
    if not row:
        return None
    return {
        "id": row["id"], "round": row["round"], "turn_index": row["turn_index"],
        "participants": json.loads(row["participants"]), "log": json.loads(row["log"]),
    }


def _save(enc: dict) -> None:
    db.execute(
        "UPDATE combat_encounters SET round=?, turn_index=?, participants=?, log=? WHERE id=?",
        [enc["round"], enc["turn_index"], json.dumps(enc["participants"]),
         json.dumps(enc["log"]), enc["id"]],
    )


# ------------------------------------------------------------------ lifecycle
def start_combat(enemies: list[dict]) -> dict:
    """Roll initiative for the party + enemies and open an encounter."""
    participants: list[dict] = []

    for pc in state.list_pcs():
        init_bonus = (pc.get("custom_dice") or {}).get("initiative_bonus", 0)
        roll = dice.roll_expression("1d20+DEX", pc=pc).total + int(init_bonus or 0)
        ab = pc.get("abilities") or {}
        prof = (pc.get("custom_dice") or {}).get("proficiency_bonus") or homebrew.proficiency_bonus(pc.get("level", 1))
        best = max(homebrew.ability_mod(ab.get("str", 10)), homebrew.ability_mod(ab.get("dex", 10)))
        participants.append({
            "id": pc["id"], "name": pc["name"], "side": "party",
            "hp": pc["hp"], "max_hp": pc["max_hp"], "ac": pc["ac"],
            "init": roll, "zone": "Engaged", "ai": "ally", "conditions": [],
            "down": pc["hp"] <= 0, "death_saves": {"success": 0, "fail": 0},
            # heroes hand control to the player; companions are DM-run allies
            "controlled": "player" if pc.get("is_player", 1) else "dm",
            "attack_bonus": prof + best,
            "damage": f"1d8{best:+d}" if best else "1d8",
        })

    for i, e in enumerate(enemies):
        spec = {**ENEMY_DEFAULTS, **e}
        roll = random.randint(1, 20)
        participants.append({
            "id": f"E{i+1}", "name": spec.get("name", f"Enemy {i+1}"), "side": "enemy",
            "hp": spec["hp"], "max_hp": spec["hp"], "ac": spec["ac"],
            "attack_bonus": spec["attack_bonus"], "damage": spec["damage"],
            "init": roll, "zone": spec["zone"], "ai": spec["ai"], "conditions": [],
            "down": False, "death_saves": {"success": 0, "fail": 0},
        })

    participants.sort(key=lambda p: p["init"], reverse=True)
    log = [f"Initiative: " + ", ".join(f"{p['name']}({p['init']})" for p in participants)]

    cur = db.execute(
        "INSERT INTO combat_encounters (status, round, turn_index, participants, log) "
        "VALUES ('active', 1, 0, ?, ?)",
        [json.dumps(participants), json.dumps(log)],
    )
    state.update_world(global_events=(state.get_world().get("global_events") or []) + ["combat"])
    return {"id": cur.lastrowid, "round": 1, "turn_index": 0,
            "participants": participants, "log": log}


def end_combat() -> None:
    row = _active_row()
    if row:
        db.execute("UPDATE combat_encounters SET status='ended' WHERE id=?", [row["id"]])
    ge = [e for e in (state.get_world().get("global_events") or []) if e != "combat"]
    state.update_world(global_events=ge)


# ------------------------------------------------------------- enemy/death AI
def _living(parts, side):
    return [p for p in parts if p["side"] == side and not p["down"]]


def _award_victory_xp(parts, log):
    """On a win, the whole party (heroes + companions) earns XP scaled to the foes
    defeated. Low for trivial mobs, meaningful for tough ones — fighting now levels you."""
    xp = sum(25 + 5 * p.get("max_hp", 0) for p in parts if p["side"] == "enemy")
    if xp <= 0:
        return
    for p in parts:
        if p["side"] == "party":
            pc = state.get_pc(p["id"])
            if pc:
                state.upsert_pc({"id": pc["id"], "xp": pc.get("xp", 0) + xp})
    log.append(f"The party earns {xp} XP from the battle.")


def _tick_conditions(parts, log):
    """Decrement timed conditions at the start of each round; drop the expired."""
    for p in parts:
        kept = []
        for c in p.get("conditions", []):
            rounds = c.get("rounds")
            if rounds is None:
                kept.append(c)  # indefinite
                continue
            rounds -= 1
            if rounds > 0:
                kept.append({**c, "rounds": rounds})
            else:
                log.append(f"{p['name']} is no longer {c.get('name','affected')}.")
        p["conditions"] = kept


def _pick_target(actor, party):
    if actor["ai"] == "tactical":
        return min(party, key=lambda p: p["hp"])  # focus the weakest
    if actor["ai"] == "berserker":
        return max(party, key=lambda p: p["hp"])  # charge the strongest/nearest
    return random.choice(party)


def _enemy_turn(actor, parts, log):
    party = _living(parts, "party")
    if not party:
        return
    # cowardly flees when bloodied
    if actor["ai"] == "cowardly" and actor["hp"] <= actor["max_hp"] * 0.25:
        actor["zone"] = "Far"
        log.append(f"{actor['name']} loses nerve and falls back.")
        return

    target = _pick_target(actor, party)

    # spellcaster opens with control
    if actor["ai"] == "spellcaster" and random.random() < 0.5:
        target["conditions"].append({"name": "Restrained", "rounds": 2})
        log.append(f"{actor['name']} binds {target['name']} (Restrained).")
        return

    atk = dice.roll_expression(f"1d20+{actor['attack_bonus']}", label="attack")
    if atk.outcome == "FUMBLE":
        log.append(f"{actor['name']} fumbles its attack on {target['name']}.")
    elif atk.total >= target["ac"] or atk.outcome == "CRIT":
        dmg = dice.roll_expression(actor["damage"], label="damage")
        amount = dmg.total * (2 if atk.outcome == "CRIT" else 1)
        target["hp"] = max(0, target["hp"] - amount)
        log.append(
            f"{actor['name']} hits {target['name']} for {amount}"
            f"{' (CRIT)' if atk.outcome=='CRIT' else ''} -> {target['hp']} HP."
        )
        if target["hp"] == 0 and not target["down"]:
            target["down"] = True
            log.append(f"{target['name']} falls and begins making death saves.")
            state.upsert_pc({"id": target["id"], "hp": 0, "status": "down"})
        else:
            state.upsert_pc({"id": target["id"], "hp": target["hp"]})
    else:
        log.append(f"{atk.total} misses {target['name']} (AC {target['ac']}).")


def _ally_turn(actor, parts, log):
    """A DM-controlled companion's combat turn — auto-attacks the weakest enemy."""
    enemies = _living(parts, "enemy")
    if not enemies:
        return
    target = min(enemies, key=lambda e: e["hp"])
    atk = dice.roll_expression(f"1d20+{actor.get('attack_bonus', 2)}", label="attack")
    if atk.outcome == "FUMBLE":
        log.append(f"{actor['name']} fumbles against {target['name']}.")
    elif atk.total >= target["ac"] or atk.outcome == "CRIT":
        dmg = dice.roll_expression(actor.get("damage", "1d8"), label="damage")
        amount = dmg.total * (2 if atk.outcome == "CRIT" else 1)
        target["hp"] = max(0, target["hp"] - amount)
        target["down"] = target["hp"] <= 0
        log.append(f"{actor['name']} strikes {target['name']} for {amount}"
                   f"{' (CRIT)' if atk.outcome == 'CRIT' else ''} -> {target['hp']} HP.")
    else:
        log.append(f"{actor['name']} misses {target['name']} ({atk.total} vs AC {target['ac']}).")


def _death_save(actor, log):
    r = dice.roll_expression("1d20", label="death save")
    if r.total == 20:
        actor["down"] = False
        actor["hp"] = 1
        actor["death_saves"] = {"success": 0, "fail": 0}
        state.upsert_pc({"id": actor["id"], "hp": 1, "status": "alive"})
        log.append(f"{actor['name']} surges back to consciousness (nat 20)!")
    elif r.total >= 10:
        actor["death_saves"]["success"] += 1
        log.append(f"{actor['name']} death save: success ({actor['death_saves']['success']}/3).")
        if actor["death_saves"]["success"] >= 3:
            log.append(f"{actor['name']} stabilizes.")
    else:
        actor["death_saves"]["fail"] += 1 if r.total > 1 else 2
        log.append(f"{actor['name']} death save: failure ({actor['death_saves']['fail']}/3).")
        if actor["death_saves"]["fail"] >= 3:
            actor["down"] = True
            state.upsert_pc({"id": actor["id"], "status": "dead"})
            log.append(f"{actor['name']} has died.")


def _advance_pointer(enc: dict, parts: list, log: list) -> None:
    enc["turn_index"] += 1
    if enc["turn_index"] >= len(parts):
        enc["turn_index"] = 0
        enc["round"] += 1
        log.append(f"— Round {enc['round']} —")
        _tick_conditions(parts, log)


def _resolve(enc: dict) -> dict:
    """Run automatic turns (enemies + PC death saves) until a conscious PC must act
    or combat ends. Stops *at* the player's turn without consuming it."""
    parts = enc["participants"]
    new_log: list[str] = []
    guard = 0

    while guard < 64:
        guard += 1
        if not _living(parts, "enemy"):
            new_log.append("The enemies are defeated.")
            _award_victory_xp(parts, new_log)
            enc["log"] += new_log
            _save(enc)
            end_combat()
            return {"ended": True, "victor": "party", "log": new_log, "encounter": status()}
        if not _living(parts, "party"):
            new_log.append("The party falls.")
            enc["log"] += new_log
            _save(enc)
            end_combat()
            return {"ended": True, "victor": "enemy", "log": new_log, "encounter": enc}

        actor = parts[enc["turn_index"]]
        if actor["side"] == "party":
            pc = state.get_pc(actor["id"])
            if actor["down"] and pc and pc["status"] != "dead":
                _death_save(actor, new_log)
            elif actor.get("controlled") == "dm" and not actor["down"]:
                _ally_turn(actor, parts, new_log)  # DM-run companion acts automatically
            else:
                enc["log"] += new_log  # conscious hero — hand control to the player
                _save(enc)
                return {"ended": False, "actor": actor, "log": new_log, "encounter": enc}
        elif not actor["down"]:
            _enemy_turn(actor, parts, new_log)

        _advance_pointer(enc, parts, new_log)

    enc["log"] += new_log
    _save(enc)
    return {"ended": False, "log": new_log, "encounter": enc}


def advance_to_player() -> dict:
    """Resolve up to the first/next conscious PC turn (used for the combat opening)."""
    enc = status()
    if enc is None:
        return {"ended": True, "log": []}
    return _resolve(enc)


def end_player_turn() -> dict:
    """The PC has acted — consume their turn, then resolve enemies/death-saves until
    it's a conscious PC's turn again (or combat ends)."""
    enc = status()
    if enc is None:
        return {"ended": True, "log": []}
    _advance_pointer(enc, enc["participants"], enc["log"])
    return _resolve(enc)


def set_enemy_hp(name: str, hp: int) -> bool:
    """Called from the mechanics layer when the DM declares ENEMY_HP."""
    enc = status()
    if enc is None:
        return False
    for p in enc["participants"]:
        if p["side"] == "enemy" and p["name"].lower() == name.lower():
            p["hp"] = max(0, hp)
            p["down"] = p["hp"] <= 0
            _save(enc)
            return True
    return False
