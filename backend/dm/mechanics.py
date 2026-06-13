"""Apply parsed `[MECHANICS]` directives to structured state — deterministically.

This is the trust boundary: the LLM *declares* changes; this module *enforces* them.
Dice are rolled here (never by the LLM). Anything the engine can't map is recorded in
`applied` as a note rather than silently dropped.
"""

from __future__ import annotations

import logging
import re
import uuid

from backend.core import db, state
from backend.core.models import Mechanic, RollResult
from backend.rules import dice, homebrew

logger = logging.getLogger("emberheart.mechanics")


def _parse_enemy(token: str) -> list[dict]:
    """Parse one `COMBAT_START` enemy token like 'Frost Wolf x2 hp7 ac13 ai:tactical'."""
    t = token.strip()
    count = 1
    mx = re.search(r"\bx(\d+)\b", t)
    if mx:
        count = max(1, min(12, int(mx.group(1))))
        t = (t[: mx.start()] + t[mx.end():])

    def num(pat: str, default: int) -> int:
        m = re.search(pat, t, re.IGNORECASE)
        return int(m.group(1)) if m else default

    hp = num(r"hp(\d+)", 10)
    ac = num(r"ac(\d+)", 12)
    atk = num(r"atk(\d+)", 3)
    dmg_m = re.search(r"dmg([0-9dn+\-]+)", t, re.IGNORECASE)
    dmg = dmg_m.group(1) if dmg_m else "1d6+1"
    ai_m = re.search(r"ai:(\w+)", t, re.IGNORECASE)
    ai = ai_m.group(1).lower() if ai_m else "berserker"
    name = re.sub(r"(hp\d+|ac\d+|atk\d+|dmg[0-9dn+\-]+|ai:\w+)", "", t, flags=re.IGNORECASE).strip()
    name = name or "Enemy"
    base = {"name": name, "hp": hp, "ac": ac, "attack_bonus": atk, "damage": dmg, "ai": ai}
    if count == 1:
        return [base]
    return [{**base, "name": f"{name} {i+1}"} for i in range(count)]


def _parse_item(parts: list[str]) -> tuple[str, int]:
    """Reconstruct an item name + quantity from comma-split args.

    The DM puts commas inside descriptions ('a curious, carved bone fragment, 1'),
    so we take a trailing pure-number token as the quantity and rejoin the rest as
    the name. A name that is *only* a number is junk and yields ('', qty).
    """
    rest = [p.strip() for p in parts if p.strip()]
    qty = 1
    if len(rest) > 1 and rest[-1].lstrip("+-").isdigit():
        qty = max(1, int(rest[-1]))
        rest = rest[:-1]
    name = ", ".join(rest).strip()
    if name.lstrip("+-").isdigit():  # bare number -> not a real item
        return "", qty
    return name, qty


def _ensure_npc(name: str, result: dict) -> dict | None:
    """Return an existing NPC by name, or auto-register a stub so it starts being
    tracked. New stubs are queued in `result['spawned']` for dossier fill."""
    name = (name or "").strip()
    if not name:
        return None
    npc = state.find_npc_by_name(name)
    if npc:
        return npc
    nid = "NPC-" + uuid.uuid4().hex[:8]
    state.upsert_npc({
        "id": nid, "name": name,
        "location_id": state.get_world().get("location_id"), "seed": 0,
    })
    result.setdefault("spawned", []).append(nid)
    return state.get_npc(nid)


def _find_pc(name: str, pcs: list[dict]) -> dict | None:
    """Resolve a PC by id, exact name, or unique partial name ("Kaelrath" matches
    "Kaelrath Emberhide"). An empty or bare-numeric token means "the hero" — tags like
    `HP_CHANGE: -5` legitimately omit the target. A real-but-unknown name (an NPC, an
    enemy, a typo) returns None so the caller can note it; falling back to the hero
    here would land the DM's `HP_CHANGE: Kryoss, -5` on the player's own sheet."""
    name = (name or "").strip().lower()
    if not pcs:
        return None
    if not name or name.lstrip("+-").isdigit():
        return pcs[0]
    for pc in pcs:
        if pc["name"].lower() == name or pc["id"].lower() == name:
            return pc
    partial = [pc for pc in pcs
               if name in pc["name"].lower() or pc["name"].lower() in name]
    return partial[0] if len(partial) == 1 else None


def _note_unknown_pc(tag: str, name: str, result: dict) -> None:
    result["notes"].append(f"{tag}: {name!r} is not a party member — not applied")


def _pc_and_item_args(args: list[str], pcs: list[dict]) -> tuple[dict | None, list[str]]:
    """Split '<pc>, <item>, <qty>' from '<item>, <qty>'. Only consume the first token as a
    PC if it actually names one; otherwise default to the hero and keep all args as the item
    (so 'ITEM_REMOVE: Wood, 500' isn't misread with 'Wood' as the character)."""
    first = (args[0] if args else "").strip().lower()
    # match an exact name/id OR a first-name token ("Kaelrath" -> "Kaelrath Emberhide"), but NOT a
    # mere substring (so an item like "Talmarr's gift" isn't misread as the character Talmarr).
    if first:
        for p in pcs:
            nm = p["name"].strip().lower()
            if first == nm or first == p["id"].lower() or first == nm.split()[0]:
                return p, args[1:]
    return (pcs[0] if pcs else None), list(args)


def _match_inv_item(inv: list[dict], name: str) -> dict | None:
    """Find the inventory entry that best matches a loosely-worded item name (exact first,
    then substring either direction) so spends actually land instead of no-op'ing."""
    t = (name or "").strip().lower()
    if not t:
        return None
    for it in inv:
        if it.get("item", "").strip().lower() == t:
            return it
    best, best_len = None, 0
    for it in inv:
        nm = it.get("item", "").strip().lower()
        if nm and (t in nm or nm in t) and min(len(t), len(nm)) > best_len:
            best, best_len = it, min(len(t), len(nm))
    return best


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class MechanicsResult(dict):
    """Bag of side-effects the orchestrator may act on after application."""


# Tags the engine recognises. Anything else is rejected, not silently dropped.
KNOWN_TAGS = {
    "HP_CHANGE", "ENEMY_HP", "ROLL_REQUEST", "SAVE_REQUEST", "CONDITION_ADD",
    "CONDITION_REMOVE", "ITEM_ADD", "ITEM_REMOVE", "XP_GRANT",
    "NPC_DISPOSITION_CHANGE", "FACTION_REP_CHANGE", "QUEST_ADD", "QUEST_UPDATE", "QUEST_COMPLETE",
    "WORLD_HOOK", "WORLD_EVENT", "NPC_SPAWN", "NPC_STATUS", "TIME_ADVANCE",
    "COMBAT_START", "COMBAT_END", "SCENE_SET", "HOOK_RESOLVE", "PARTY_JOIN", "SKILL_XP",
    "JOURNAL", "MATERIAL_GAIN", "MATERIAL_SPEND", "MOUNT_TAME", "KINGDOM_CHANGE",
    "BUILDING_PROPOSE", "CREW_SET",
}

_BUILDING_CATEGORIES = {"defense", "divine", "leadership", "sustenance", "industry",
                        "civilian", "infrastructure"}

# stat-name synonyms for KINGDOM_CHANGE
_KINGDOM_ALIASES = {
    "pop": "population", "people": "population", "populace": "population", "citizens": "population",
    "gold": "treasury", "coin": "treasury", "coins": "treasury", "gp": "treasury", "money": "treasury",
    "army": "military", "troops": "military", "soldiers": "military", "men": "military",
    "happiness": "morale", "mood": "morale", "spirits": "morale", "unrest": "morale",
    "infra": "infrastructure", "buildings": "infrastructure",
}

# Tags whose Nth arg must contain an integer; lint before applying.
_NUMERIC_ARG = {"HP_CHANGE": 1, "ENEMY_HP": 1, "XP_GRANT": -1,
                "NPC_DISPOSITION_CHANGE": 1, "FACTION_REP_CHANGE": 1,
                "MATERIAL_GAIN": 1, "MATERIAL_SPEND": 1, "KINGDOM_CHANGE": 1}

_INT_RE = re.compile(r"[+-]?\d+")


def _coerce_int(s: str | None, default: int = 0) -> int:
    """Extract the leading signed integer from a string.

    Small models love to annotate numbers ('+5 (Trust/Urgency)', '8 damage'); we take
    the number and ignore the prose rather than rejecting the whole directive.
    """
    if s is None:
        return default
    m = _INT_RE.search(str(s))
    return int(m.group()) if m else default


_QUEST_STATUS = {
    "complete": "completed", "completed": "completed", "done": "completed",
    "finished": "completed", "closed": "completed", "close": "completed",
    "fail": "failed", "failed": "failed",
    "active": "active", "ongoing": "active", "reopen": "active",
}


def _find_quest(title: str) -> dict | None:
    """Match a quest by title — exact (case-insensitive) first, then a UNIQUE substring
    match so a paraphrased title still resolves instead of silently no-opping."""
    t = (title or "").strip()
    if not t:
        return None
    row = db.query_one("SELECT * FROM quests WHERE title = ? COLLATE NOCASE", [t])
    if row:
        return row
    rows = db.query(
        "SELECT * FROM quests WHERE title LIKE ? COLLATE NOCASE AND status != 'completed'",
        [f"%{t}%"],
    )
    return rows[0] if len(rows) == 1 else None


# Synonyms the model invents -> canonical tags. (Damage/heal handled separately so the
# sign is right.) Add to this map whenever a useful unknown tag keeps showing up.
_ALIASES = {
    "ITEM_GAINED": "ITEM_ADD", "GAIN_ITEM": "ITEM_ADD", "ITEM_GET": "ITEM_ADD",
    "LOOT": "ITEM_ADD", "ITEM_FOUND": "ITEM_ADD", "ADD_ITEM": "ITEM_ADD", "ACQUIRE": "ITEM_ADD",
    "ITEM_LOST": "ITEM_REMOVE", "LOSE_ITEM": "ITEM_REMOVE", "ITEM_USED": "ITEM_REMOVE",
    "REMOVE_ITEM": "ITEM_REMOVE", "USE_ITEM": "ITEM_REMOVE", "CONSUME": "ITEM_REMOVE",
    "LOCATION": "SCENE_SET", "LOCATION_CHANGE": "SCENE_SET", "SET_LOCATION": "SCENE_SET",
    "MOVE": "SCENE_SET", "TRAVEL": "SCENE_SET", "SET_SCENE": "SCENE_SET", "SCENE": "SCENE_SET",
    "RELATIONSHIP_CHANGE": "NPC_DISPOSITION_CHANGE", "RELATIONSHIP": "NPC_DISPOSITION_CHANGE",
    "DISPOSITION": "NPC_DISPOSITION_CHANGE", "DISPOSITION_CHANGE": "NPC_DISPOSITION_CHANGE",
    "NPC_RELATION": "NPC_DISPOSITION_CHANGE", "ATTITUDE": "NPC_DISPOSITION_CHANGE",
    "REPUTATION": "FACTION_REP_CHANGE", "REP_CHANGE": "FACTION_REP_CHANGE",
    "REPUTATION_CHANGE": "FACTION_REP_CHANGE",
    "QUEST": "QUEST_ADD", "NEW_QUEST": "QUEST_ADD", "ADD_QUEST": "QUEST_ADD", "QUEST_START": "QUEST_ADD",
    "QUEST_PROGRESS": "QUEST_UPDATE", "UPDATE_QUEST": "QUEST_UPDATE",
    "QUEST_DONE": "QUEST_COMPLETE", "COMPLETE_QUEST": "QUEST_COMPLETE",
    "FINISH_QUEST": "QUEST_COMPLETE", "QUEST_FINISH": "QUEST_COMPLETE", "QUEST_CLOSE": "QUEST_COMPLETE",
    "ROLL": "ROLL_REQUEST", "CHECK": "ROLL_REQUEST", "SKILL_CHECK": "ROLL_REQUEST",
    "ABILITY_CHECK": "ROLL_REQUEST", "REQUEST_ROLL": "ROLL_REQUEST",
    "SAVE": "SAVE_REQUEST", "SAVING_THROW": "SAVE_REQUEST", "SAVE_THROW": "SAVE_REQUEST",
    "TIME": "TIME_ADVANCE", "ADVANCE_TIME": "TIME_ADVANCE", "TIME_PASS": "TIME_ADVANCE",
    "TIME_SKIP": "TIME_ADVANCE", "PASS_TIME": "TIME_ADVANCE",
    "HOOK": "WORLD_HOOK", "FORESHADOW": "WORLD_HOOK", "SEED": "WORLD_HOOK", "PLOT_HOOK": "WORLD_HOOK",
    "EVENT": "WORLD_EVENT",
    "CONDITION": "CONDITION_ADD", "STATUS_EFFECT": "CONDITION_ADD", "EFFECT_ADD": "CONDITION_ADD",
    "ADD_CONDITION": "CONDITION_ADD", "AFFLICT": "CONDITION_ADD", "APPLY_CONDITION": "CONDITION_ADD",
    "CONDITION_CLEAR": "CONDITION_REMOVE", "REMOVE_CONDITION": "CONDITION_REMOVE", "CURE": "CONDITION_REMOVE",
    "XP": "XP_GRANT", "EXPERIENCE": "XP_GRANT", "XP_GAIN": "XP_GRANT", "GRANT_XP": "XP_GRANT",
    "AWARD_XP": "XP_GRANT", "XP_AWARD": "XP_GRANT",
    "SKILL_GAIN": "SKILL_XP", "SKILL_LEVEL": "SKILL_XP", "TRAIN": "SKILL_XP",
    "CRAFT_XP": "SKILL_XP", "SKILL_PROGRESS": "SKILL_XP",
    "NPC": "NPC_SPAWN", "NEW_NPC": "NPC_SPAWN", "INTRODUCE_NPC": "NPC_SPAWN", "SPAWN_NPC": "NPC_SPAWN",
    "ADD_NPC": "NPC_SPAWN", "CREATE_NPC": "NPC_SPAWN",
    "ENEMY": "ENEMY_HP", "ENEMY_DAMAGE": "ENEMY_HP", "ENEMY_HEALTH": "ENEMY_HP",
    "COMBAT": "COMBAT_START", "START_COMBAT": "COMBAT_START", "BEGIN_COMBAT": "COMBAT_START", "FIGHT": "COMBAT_START",
    "END_COMBAT": "COMBAT_END", "COMBAT_OVER": "COMBAT_END",
    "RECRUIT": "PARTY_JOIN", "JOIN_PARTY": "PARTY_JOIN", "PARTY_ADD": "PARTY_JOIN", "COMPANION_JOIN": "PARTY_JOIN",
    "RESOLVE_HOOK": "HOOK_RESOLVE", "HOOK_PAID": "HOOK_RESOLVE", "HOOK_RESOLVED": "HOOK_RESOLVE",
    "JOURNAL_ENTRY": "JOURNAL", "DIARY": "JOURNAL", "FEELING": "JOURNAL", "FEELS": "JOURNAL",
    "REFLECTION": "JOURNAL", "INNER": "JOURNAL", "HEART": "JOURNAL",
    "GATHER": "MATERIAL_GAIN", "HARVEST": "MATERIAL_GAIN", "RESOURCE_ADD": "MATERIAL_GAIN",
    "MATERIAL_ADD": "MATERIAL_GAIN", "STORE_ADD": "MATERIAL_GAIN", "RESOURCE_GAIN": "MATERIAL_GAIN",
    "USE_MATERIAL": "MATERIAL_SPEND", "CONSUME_MATERIAL": "MATERIAL_SPEND",
    "MATERIAL_USE": "MATERIAL_SPEND", "MATERIAL_REMOVE": "MATERIAL_SPEND",
    "RESOURCE_SPEND": "MATERIAL_SPEND", "SPEND_MATERIAL": "MATERIAL_SPEND",
    "TAME": "MOUNT_TAME", "MOUNT": "MOUNT_TAME", "MOUNT_ADD": "MOUNT_TAME",
    "NEW_MOUNT": "MOUNT_TAME", "MOUNT_NEW": "MOUNT_TAME",
    "KINGDOM": "KINGDOM_CHANGE", "REALM_CHANGE": "KINGDOM_CHANGE", "REALM": "KINGDOM_CHANGE",
    "DOMAIN_CHANGE": "KINGDOM_CHANGE", "KINGDOM_UPDATE": "KINGDOM_CHANGE",
    "PROPOSE_BUILDING": "BUILDING_PROPOSE", "NEW_BUILDING": "BUILDING_PROPOSE",
    "BUILDING_ADD": "BUILDING_PROPOSE", "ADD_BUILDING": "BUILDING_PROPOSE",
    "CREW": "CREW_SET", "CREW_ADD": "CREW_SET", "TEAM": "CREW_SET",
    "TEAM_ADD": "CREW_SET", "TEAM_SET": "CREW_SET",
}
_DAMAGE_TAGS = {"DAMAGE", "TAKE_DAMAGE", "HP_LOSS", "HURT", "WOUND", "DAMAGE_TAKEN"}
_HEAL_TAGS = {"HEAL", "HP_GAIN", "HP_RESTORE", "RESTORE", "RECOVER", "HEALING"}


def _canonicalize(mech: Mechanic) -> Mechanic:
    """Map an invented synonym onto a real tag (fixing damage/heal sign)."""
    tag, args = mech.tag, list(mech.args)
    if tag in _DAMAGE_TAGS and len(args) >= 2:
        args[1] = str(-abs(_coerce_int(args[1])))
        return Mechanic(tag="HP_CHANGE", args=args, raw=mech.raw)
    if tag in _HEAL_TAGS and len(args) >= 2:
        args[1] = str(abs(_coerce_int(args[1])))
        return Mechanic(tag="HP_CHANGE", args=args, raw=mech.raw)
    if tag in _ALIASES:
        return Mechanic(tag=_ALIASES[tag], args=args, raw=mech.raw)
    return mech


def _lint(mech: Mechanic) -> str | None:
    """Return a rejection reason for a *known* tag, or None if well-formed."""
    idx = _NUMERIC_ARG.get(mech.tag)
    if idx is not None and mech.args:
        try:
            target = mech.args[idx]
        except IndexError:
            return f"{mech.tag} missing numeric arg"
        if _INT_RE.search(target) is None:  # no number anywhere -> genuinely malformed
            return f"{mech.tag} expected a number, got {target!r}"
    return None


def apply_mechanics(mechanics: list[Mechanic], *, acting_pc_id: str | None = None) -> MechanicsResult:
    pcs = state.list_pcs()
    # a stale/unknown acting id still means "the hero acts" — this is plumbing, not a DM tag
    acting = (_find_pc(acting_pc_id or "", pcs) or pcs[0]) if pcs else None

    applied: list[str] = []
    rolls: list[RollResult] = []
    rejected: list[str] = []
    notes: list[str] = []
    result = MechanicsResult(
        applied=applied, rolls=rolls, rejected=rejected, notes=notes,
        combat_start=False, combat_end=False, time_advance=None, spawned=[],
    )

    for mech in mechanics:
        mech = _canonicalize(mech)  # remap invented synonyms onto real tags
        if mech.tag not in KNOWN_TAGS:
            # Unrecognized but not malformed: capture it as a note instead of an error,
            # so nothing is silently lost and the player can see what the DM intended.
            logger.info("noted unrecognized tag: %s", mech.raw)
            notes.append(mech.raw)
            continue
        reason = _lint(mech)
        if reason:
            logger.info("rejected mechanic %r: %s", mech.raw, reason)
            rejected.append(f"{mech.raw} — {reason}")
            continue
        try:
            _dispatch(mech.tag, mech.args, pcs, acting, applied, rolls, result)
        except Exception as exc:  # noqa: BLE001 - one bad tag must not abort the turn
            logger.warning("mechanic %s failed: %s", mech.raw, exc)
            rejected.append(f"{mech.raw} — error: {exc}")

    return result


def _dispatch(tag, args, pcs, acting, applied, rolls, result):  # noqa: C901 - flat dispatch
    if tag == "HP_CHANGE" and len(args) >= 2:
        pc = _find_pc(args[0], pcs)
        if pc:
            delta = _coerce_int(args[1])
            new = _clamp(pc["hp"] + delta, 0, pc["max_hp"])
            state.upsert_pc({"id": pc["id"], "hp": new,
                             "status": "down" if new == 0 else "alive"})
            applied.append(f"{pc['name']} HP {pc['hp']}->{new}")
        else:
            _note_unknown_pc(tag, args[0], result)

    elif tag == "SKILL_XP" and len(args) >= 2:
        # SKILL_XP: <skill>, <amount>   or   <pc>, <skill>, <amount>
        if len(args) >= 3:
            target, skill, amt = _find_pc(args[0], pcs), args[1], _coerce_int(args[2])
            if target is None:
                _note_unknown_pc(tag, args[0], result)
        else:
            target, skill, amt = acting, args[0], _coerce_int(args[1])
        if target and amt:
            r = state.grant_skill_xp(target["id"], skill, amt)
            if r:
                applied.append(f"{target['name']} {r['skill']} +{amt}xp → lvl {r['level']}"
                               + (" (up!)" if r["leveled"] else ""))

    elif tag == "XP_GRANT":
        amount = _coerce_int(args[-1])
        if len(args) >= 2 and args[0].strip().lower() in ("party", "all", "everyone"):
            targets = pcs
        elif len(args) >= 2:
            targets = [_find_pc(args[0], pcs)]
            if targets == [None]:
                _note_unknown_pc(tag, args[0], result)
        else:
            targets = pcs
        for pc in filter(None, targets):
            xp = pc["xp"] + amount
            lvl = homebrew.char_level_for_xp(xp)
            state.upsert_pc({"id": pc["id"], "xp": xp})
            note = f"{pc['name']} +{amount} XP (total {xp})"
            if lvl > pc["level"]:
                note += f" — eligible for level {lvl} (GM confirm)"
            applied.append(note)

    elif tag in ("ROLL_REQUEST", "SAVE_REQUEST"):
        # SAVE_REQUEST: ABILITY, DC[, label]  |  ROLL_REQUEST: expr, label
        if tag == "SAVE_REQUEST" and args:
            ability = args[0].upper()
            dc = _coerce_int(args[1], None) if len(args) > 1 else None
            label = args[2] if len(args) > 2 else f"{ability} save"
            r = dice.roll_expression(f"1d20+{ability}", pc=acting, dc=dc, label=label)
        else:
            expr = args[0] if args else "1d20"
            label = args[1] if len(args) > 1 else expr
            r = dice.roll_expression(expr, pc=acting, label=label)
        rolls.append(r)
        applied.append(dice.format_result(r))

    elif tag == "CONDITION_ADD" and len(args) >= 2:
        pc = _find_pc(args[0], pcs)
        if pc:
            # the condition name may itself contain commas ("poisoned, weakened"); only a
            # *trailing pure-number* token is the duration in rounds (same rule as items).
            parts = [a.strip() for a in args[1:] if a.strip()]
            rounds = None
            if len(parts) > 1 and parts[-1].lstrip("+-").isdigit():
                rounds = int(parts[-1])
                parts = parts[:-1]
            name = ", ".join(parts)
            # dedupe: re-applying a condition REFRESHES its duration, not stacks duplicates
            existing = [c for c in pc["conditions"] if c.get("name", "").lower() == name.lower()]
            conds = [c for c in pc["conditions"] if c.get("name", "").lower() != name.lower()]
            conds.append({"name": name, "rounds": rounds})
            state.upsert_pc({"id": pc["id"], "conditions": conds})
            applied.append(f"{pc['name']} {'refreshes' if existing else 'gains'} {name}")
        else:
            _note_unknown_pc(tag, args[0], result)

    elif tag == "CONDITION_REMOVE" and len(args) >= 2:
        pc = _find_pc(args[0], pcs)
        if pc:
            conds = [c for c in pc["conditions"] if c.get("name", "").lower() != args[1].lower()]
            state.upsert_pc({"id": pc["id"], "conditions": conds})
            applied.append(f"{pc['name']} loses {args[1]}")
        else:
            _note_unknown_pc(tag, args[0], result)

    elif tag == "ITEM_ADD" and len(args) >= 2:
        pc, item_args = _pc_and_item_args(args, pcs)
        if pc:
            item, qty = _parse_item(item_args)
            if item:  # skip bare-number junk (commas inside descriptions used to mangle this)
                inv = [dict(i) for i in pc["inventory"]]
                for it in inv:  # merge into an existing stack instead of making a duplicate
                    if it.get("item", "").strip().lower() == item.lower():
                        it["qty"] = it.get("qty", 1) + qty
                        break
                else:
                    inv.append({"item": item, "qty": qty})
                state.upsert_pc({"id": pc["id"], "inventory": inv})
                applied.append(f"{pc['name']} +{qty} {item}")

    elif tag == "ITEM_REMOVE" and args:
        pc, item_args = _pc_and_item_args(args, pcs)
        if pc:
            item, qty = _parse_item(item_args)
            match = _match_inv_item(pc["inventory"], item) if item else None
            if match:
                have = int(match.get("qty", 1))
                take = have if (qty >= have) else qty   # qty defaults to 1; respect explicit amounts
                inv = []
                for it in pc["inventory"]:
                    if it is match and take < have:
                        inv.append({**it, "qty": have - take})
                    elif it is not match:
                        inv.append(it)
                state.upsert_pc({"id": pc["id"], "inventory": inv})
                applied.append(f"{pc['name']} -{take} {match['item']}")
            elif item:
                notes.append(f"ITEM_REMOVE: '{item}' not in {pc['name']}'s pack — nothing removed")

    elif tag == "NPC_DISPOSITION_CHANGE" and len(args) >= 2:
        npc = _ensure_npc(args[0], result)  # auto-register if the DM names someone new
        if npc and acting:
            val = state.set_npc_disposition(npc["id"], acting["id"], _coerce_int(args[1]))
            applied.append(f"{npc['name']} disposition -> {val}")

    elif tag == "FACTION_REP_CHANGE" and len(args) >= 2 and acting:
        val = state.change_faction_rep(args[0], acting["id"], _coerce_int(args[1]))
        if val is not None:
            applied.append(f"reputation with {args[0]} -> {val}")

    elif tag == "QUEST_ADD" and args:
        qid = "Q-" + uuid.uuid4().hex[:8]
        state.upsert_quest({"id": qid, "title": args[0],
                            "description": args[1] if len(args) > 1 else ""})
        applied.append(f"new quest: {args[0]}")

    elif tag == "QUEST_COMPLETE" and args:
        row = _find_quest(args[0])
        if row:
            state.upsert_quest({"id": row["id"], "status": "completed"})
            applied.append(f"quest completed: {row['title']}")
        else:
            result["notes"].append(f"QUEST_COMPLETE: no open quest matching '{args[0]}'")

    elif tag == "QUEST_UPDATE" and args:
        row = _find_quest(args[0])
        if row:
            note = (args[1] if len(args) > 1 else "").strip()
            status = _QUEST_STATUS.get(note.lower())
            if status:
                state.upsert_quest({"id": row["id"], "status": status})
            applied.append(f"quest '{row['title']}' {('-> ' + status) if status else 'updated: ' + note}")
        else:
            result["notes"].append(f"QUEST_UPDATE: no quest matching '{args[0]}'")

    elif tag == "WORLD_HOOK" and args:
        # rejoin the whole description — the DM uses commas inside it, which used to
        # truncate the hook at the first comma.
        desc = ", ".join(a.strip() for a in args if a.strip())
        state.add_hook(desc, "", state.get_world().get("turn_counter", 0))
        applied.append(f"hook seeded: {desc[:60]}")

    elif tag == "HOOK_RESOLVE" and args:
        ref = ", ".join(a.strip() for a in args if a.strip())
        n = state.resolve_hook(ref)
        applied.append(f"hook resolved: {ref[:50]}" if n else f"(no matching hook: {ref[:40]})")

    elif tag == "WORLD_EVENT" and args:
        world = state.get_world()
        events = world.get("global_events") or []
        events.append({"event": args[0], "status": args[1] if len(args) > 1 else "triggered"})
        state.update_world(global_events=events)
        applied.append(f"world event: {args[0]}")

    elif tag == "NPC_SPAWN" and args:
        existing = state.find_npc_by_name(args[0])
        if existing:
            applied.append(f"{args[0]} already known")  # dedupe: don't re-create
        else:
            nid = "NPC-" + uuid.uuid4().hex[:8]
            state.upsert_npc({
                "id": nid, "name": args[0], "role": args[1] if len(args) > 1 else "",
                "domains": args[2].split("/") if len(args) > 2 else [],
                "location_id": state.get_world().get("location_id"), "seed": 0,
            })
            result["spawned"].append(nid)
            applied.append(f"NPC spawned: {args[0]}")

    elif tag == "NPC_STATUS" and len(args) >= 2:
        npc = _ensure_npc(args[0], result)
        if npc:
            state.set_npc_status(npc["id"], args[1])
            applied.append(f"{npc['name']} is now {args[1]}")

    elif tag == "PARTY_JOIN" and args:
        npc = state.find_npc_by_name(args[0])
        if npc and npc.get("status") != "party":
            pc = state.promote_npc_to_party(npc["id"])
            applied.append(f"{npc['name']} joins the party as a companion" if pc
                           else f"(could not recruit {args[0]})")
        else:
            applied.append(f"({args[0]} is not an available NPC to recruit)")

    elif tag == "TIME_ADVANCE" and args:
        amount = _coerce_int(args[0], 1)
        unit = args[1] if len(args) > 1 else "hours"
        result["time_advance"] = (amount, unit)
        applied.append(f"time advances {amount} {unit}")

    elif tag == "SCENE_SET" and args:
        # the DM declares where the party is / what's happening, so working memory
        # stays grounded and the story doesn't drift (one short line)
        scene = ", ".join(args).strip()
        state.update_world(scene=scene)
        if len(args) > 1 and args[-1].lower().startswith("loc:"):
            pass  # reserved for future explicit location linkage
        applied.append(f"scene: {scene[:60]}")

    elif tag == "JOURNAL" and args:
        # the DM logs a reflective "feels" beat to the hero's journal.
        # format: JOURNAL: <mood>, <reflection...>  (commas in the body are rejoined)
        if len(args) >= 2:
            mood = args[0].strip()[:24]
            body = ", ".join(a for a in args[1:]).strip()
        else:
            mood, body = "", args[0].strip()
        if body:
            title = " ".join(body.split()[:6]).rstrip(".,;:") + ("…" if len(body.split()) > 6 else "")
            state.add_journal(title, body, mood=mood, author="Kaelrath")
            applied.append(f"journal: {body[:50]}")

    elif tag == "MATERIAL_GAIN" and len(args) >= 2:
        # the camp gathers/produces a raw resource (folds into the idle larder)
        qty = abs(_coerce_int(args[1], 0))
        if qty:
            new = state.adjust_material(args[0], qty)
            applied.append(f"+{qty} {state.normalize_material(args[0]).replace('_',' ')} (stores: {new})")

    elif tag == "MATERIAL_SPEND" and len(args) >= 2:
        # the story consumes from the camp stores
        qty = abs(_coerce_int(args[1], 0))
        if qty:
            new = state.adjust_material(args[0], -qty)
            applied.append(f"-{qty} {state.normalize_material(args[0]).replace('_',' ')} (stores: {new})")

    elif tag == "KINGDOM_CHANGE" and len(args) >= 2:
        # the DM moves the realm's ledger from the story (festival, war, plague, harvest...).
        # uses only the public kingdom API so it survives the dashboard rebuild underneath.
        from backend.sim import kingdom

        with kingdom.DOMAIN_LOCK:   # read-modify-write must not interleave with ticks/UI
            dom = kingdom.get_domain()
            if dom is not None:
                stat = args[0].strip().lower()
                stat = _KINGDOM_ALIASES.get(stat, stat)
                delta = _coerce_int(args[1], 0)
                top = {"population", "treasury", "military", "morale", "infrastructure"}
                if delta and stat in top:
                    new = dom.get(stat, 0) + delta
                    new = _clamp(new, 1, 5) if stat == "morale" else max(0, new)
                    dom[stat] = new
                    kingdom.set_domain(dom)
                    applied.append(f"kingdom {stat} {'+' if delta >= 0 else ''}{delta} -> {new}")
                elif delta:  # otherwise treat it as a stockpile (food/lumber/ore/supplies/...)
                    key = stat.split(".", 1)[1] if stat.startswith("stockpiles") else stat
                    stocks = dom.setdefault("stockpiles", {})
                    stocks[key] = max(0, stocks.get(key, 0) + delta)
                    kingdom.set_domain(dom)
                    applied.append(f"kingdom stores {key} {'+' if delta >= 0 else ''}{delta} "
                                   f"-> {stocks[key]}")

    elif tag == "BUILDING_PROPOSE" and args:
        # the council/story proposes a new building -> it becomes buildable in the Kingdom tab
        from backend.sim import kingdom

        label = args[0].strip()
        cat = args[1].strip().lower() if len(args) > 1 and args[1].strip() else "civilian"
        if cat not in _BUILDING_CATEGORIES:
            cat = "civilian"
        desc = ", ".join(a for a in args[2:]).strip()
        if label:
            kingdom.add_building(label, category=cat, desc=desc)
            applied.append(f"proposed building: {label} (now buildable in the Kingdom tab)")

    elif tag == "CREW_SET" and args:
        # the council stands up / resizes a named crew. format: CREW_SET: <name>, <size?>, <role?>
        from backend.sim import kingdom

        name = args[0].strip()
        size = 0
        for a in args[1:]:
            if a.strip().lstrip("+-").isdigit():
                size = int(a.strip())
                break
        role = ", ".join(a.strip() for a in args[1:]
                         if a.strip() and not a.strip().lstrip("+-").isdigit())
        if name:
            kingdom.add_crew(name, size=size, role=role)
            applied.append(f"crew: {name}" + (f" ({size})" if size else "") + " — set in the Labor tab")

    elif tag == "MOUNT_TAME" and args:
        # the hero tames/bonds a mount. format: MOUNT_TAME: <name>, <kind?>, <trait?>...
        import uuid as _uuid
        name = args[0].strip()
        if name and not state.find_mount_by_name(name):
            kind = args[1].strip() if len(args) > 1 and args[1].strip() else "horse"
            traits = [a.strip() for a in args[2:] if a.strip()]
            owner = pcs[0]["id"] if pcs else None
            state.upsert_mount({"id": "MNT-" + _uuid.uuid4().hex[:6], "name": name, "kind": kind,
                                "owner_pc_id": owner, "hp": 15, "max_hp": 15, "speed": 60,
                                "traits": traits, "status": "active", "active": 1, "bond": 1})
            applied.append(f"tamed a mount: {name} ({kind})")

    elif tag == "COMBAT_START":
        result["combat_start"] = True
        enemies = []
        for token in args:
            enemies.extend(_parse_enemy(token))
        result["combat_enemies"] = enemies
        applied.append("combat begins" + (f" vs {len(enemies)} foe(s)" if enemies else ""))

    elif tag == "COMBAT_END":
        result["combat_end"] = True
        applied.append("combat ends")

    elif tag == "ENEMY_HP" and len(args) >= 2:
        from backend.sim import combat

        hp = _coerce_int(args[1])
        tracked = combat.set_enemy_hp(args[0], hp)
        applied.append(f"enemy {args[0]} HP -> {hp}" + ("" if tracked else " (no active combat)"))

    else:
        # a known tag that fell through every branch — usually malformed/too-few args.
        # nothing changed, so it belongs in notes (like unrecognized tags), not `applied`.
        result["notes"].append(f"(unhandled {tag}: {', '.join(args)})")
