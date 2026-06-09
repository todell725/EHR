"""Character progression — deterministic level-ups the engine owns (not the LLM).

The DM kept fumbling the meta-level (HP, proficiency, what features a character has), so
leveling lives here: the app computes the automatic gains and offers the *choices*
(ASI/feat, expertise, spells, subclass options); the player picks; we apply.

Classes are data-driven. **Rogue** (+ the **Soulknife** subclass) is encoded fully because
that's the player's character; any other class falls back to generic gains (HP +
proficiency) and free-form custom features, so it still works — just without a curated
feature list.
"""

from __future__ import annotations

import math
from typing import Any

from backend.rules import homebrew

# average hit-die roll per class (rounded up, 5e convention)
HIT_DIE_AVG = {"rogue": 5, "fighter": 6, "wizard": 4, "cleric": 5, "barbarian": 7}
DEFAULT_HIT_AVG = 5

# A small, rogue-flavored feat list for ASI levels.
FEATS = [
    ("Alert", "+5 initiative; can't be surprised while conscious."),
    ("Lucky", "3 luck points to reroll d20s."),
    ("Mobile", "+10 speed; no opportunity attacks from foes you melee."),
    ("Tough", "+2 HP per level."),
    ("Skulker", "Hide when lightly obscured; misses don't reveal you."),
    ("Defensive Duelist", "Add proficiency to AC as a reaction when wielding finesse."),
    ("Resilient (Con)", "+1 CON and proficiency in CON saves."),
    ("Skill Expert", "+1 ability, a skill proficiency, and one expertise."),
    ("Fey Touched", "+1 INT/WIS/CHA; learn Misty Step + a 1st-level spell."),
    ("Piercer", "Reroll one damage die once per turn; crit adds a die."),
]


def _feat(name: str, desc: str, level: int, ftype: str = "feature") -> dict:
    return {"name": name, "desc": desc, "type": ftype, "level": level}


# Soulknife psionic energy die by character level.
def _psionic(level: int) -> dict | None:
    if level < 3:
        return None
    die = "d6"
    if level >= 17:
        die = "d12"
    elif level >= 11:
        die = "d10"
    elif level >= 5:
        die = "d8"
    return {"die": die, "pool": 2 * homebrew.proficiency_bonus(level)}


def _sneak_attack(level: int) -> str:
    return f"{math.ceil(level / 2)}d6"


# Auto features granted on reaching a given Rogue level (Soulknife folded in).
_ROGUE_AUTO = {
    1: [("Sneak Attack", "Extra 1d6 when you have advantage or an ally is adjacent."),
        ("Thieves' Cant", "A secret code of rogues and vagabonds.")],
    2: [("Cunning Action", "Dash, Disengage, or Hide as a bonus action.")],
    3: [("Psychic Blades", "Manifest shimmering psychic blades; throw or strike (Soulknife)."),
        ("Psionic Power", "A pool of Psionic Energy dice fuels Soulknife tricks.")],
    5: [("Uncanny Dodge", "Halve the damage of one attack you can see, as a reaction.")],
    7: [("Evasion", "Take no damage on a successful DEX save (half on failure).")],
    9: [("Soul Blades", "Homing Strikes (add a psi die to miss) & Psychic Teleportation.")],
    11: [("Reliable Talent", "Treat any proficient skill d20 of 9 or lower as a 10.")],
    13: [("Psychic Veil", "Turn invisible for up to 1 hour using a psi die.")],
    14: [("Blindsense", "Sense hidden/invisible creatures within 10 ft.")],
    15: [("Slippery Mind", "Gain proficiency in WIS saving throws.")],
    17: [("Rend Mind", "Force a creature you Sneak Attack to make a stun save.")],
    18: [("Elusive", "No attack roll has advantage against you while you're not incapacitated.")],
    20: [("Stroke of Luck", "Once per rest, turn a miss into a hit or a failed check into a 20.")],
}
# Levels that grant an Ability Score Improvement / Feat (5e Rogue: extra at 10).
_ASI_LEVELS = {4, 8, 10, 12, 16, 19}
# Levels that grant Expertise (choose 2 skills).
_EXPERTISE_LEVELS = {1, 6}


def _is_rogue(pc: dict) -> bool:
    return (pc.get("class") or "").strip().lower() == "rogue"


def can_level_up(pc: dict) -> bool:
    """Eligible by XP (5e thresholds). GM may still force it via the API."""
    return homebrew.char_level_for_xp(pc.get("xp", 0)) > pc.get("level", 1)


def preview(pc: dict) -> dict:
    """What the next level grants + the choices the player must make."""
    cur = pc.get("level", 1)
    new = cur + 1
    con_mod = homebrew.ability_mod((pc.get("abilities") or {}).get("con", 10))
    hp_gain = HIT_DIE_AVG.get((pc.get("class") or "").lower(), DEFAULT_HIT_AVG) + con_mod

    auto: list[dict] = []
    choices: list[dict] = []

    if _is_rogue(pc):
        for name, desc in _ROGUE_AUTO.get(new, []):
            auto.append(_feat(name, desc, new))
        if new in _EXPERTISE_LEVELS:
            choices.append({
                "key": f"expertise_{new}", "type": "expertise", "pick": 2,
                "prompt": "Choose 2 skills to gain Expertise (double proficiency)",
                "options": homebrew.IDLE_SKILLS,
            })
        if new in _ASI_LEVELS:
            choices.append({
                "key": f"asi_{new}", "type": "asi",
                "prompt": "Ability Score Improvement (+2 total) or take a Feat",
                "abilities": homebrew.ABILITIES,
                "feats": [{"name": n, "desc": d} for n, d in FEATS],
            })
    # (generic / non-rogue classes: just the numbers — features are added by hand or via
    # the custom-feature slot, so we don't emit a placeholder "Level gain" entry)

    return {
        "new_level": new,
        "hp_gain": max(1, hp_gain),
        "proficiency_bonus": homebrew.proficiency_bonus(new),
        "sneak_attack": _sneak_attack(new) if _is_rogue(pc) else None,
        "psionic": _psionic(new) if _is_rogue(pc) else None,
        "auto_features": auto,
        "choices": choices,
        "allows_custom": True,
    }


def apply(pc: dict, picks: dict[str, Any]) -> dict:
    """Apply a previewed level-up + the player's picks. Returns the PC patch to upsert."""
    p = preview(pc)
    new_level = p["new_level"]
    abilities = dict(pc.get("abilities") or {})
    custom_dice = dict(pc.get("custom_dice") or {})
    features = list(pc.get("features") or [])
    log: list[str] = [f"Reached level {new_level}."]

    new_max = pc.get("max_hp", 0) + p["hp_gain"]
    custom_dice["proficiency_bonus"] = p["proficiency_bonus"]
    if p["sneak_attack"]:
        custom_dice["sneak_attack"] = p["sneak_attack"]
    if p["psionic"]:
        custom_dice["psionic_power_die"] = p["psionic"]["die"]
        custom_dice["psionic_pool"] = p["psionic"]["pool"]

    features.extend(p["auto_features"])
    log.append(f"+{p['hp_gain']} max HP; proficiency +{p['proficiency_bonus']}.")

    for choice in p["choices"]:
        sel = picks.get(choice["key"])
        if choice["type"] == "expertise" and isinstance(sel, list):
            for skill in sel[: choice["pick"]]:
                features.append(_feat(f"Expertise: {skill}", "Double proficiency.",
                                      new_level, "expertise"))
            log.append("Expertise: " + ", ".join(sel[: choice["pick"]]))
        elif choice["type"] == "asi" and isinstance(sel, dict):
            if sel.get("mode") == "feat" and sel.get("feat"):
                fdesc = next((d for n, d in FEATS if n == sel["feat"]), "")
                features.append(_feat(sel["feat"], fdesc, new_level, "feat"))
                log.append(f"Feat: {sel['feat']}")
            else:  # ASI: {abilities: {dex:1, con:1}}
                for ab, amt in (sel.get("abilities") or {}).items():
                    abilities[ab] = min(20, abilities.get(ab, 10) + int(amt))
                log.append("ASI: " + ", ".join(f"+{v} {k.upper()}"
                                                for k, v in (sel.get("abilities") or {}).items()))

    # custom homebrew features/spells/actions the player added
    for c in picks.get("custom", []) or []:
        if c.get("name"):
            features.append(_feat(c["name"], c.get("desc", ""), new_level,
                                  c.get("type", "action")))
            log.append(f"Gained: {c['name']}")

    patch = {
        "id": pc["id"], "level": new_level, "max_hp": new_max, "hp": new_max,
        "abilities": abilities, "custom_dice": custom_dice, "features": features,
    }
    return {"patch": patch, "log": log}


def seed_starting_features(pc: dict) -> list[dict]:
    """Auto class features for a character's CURRENT level (to backfill a fresh sheet)."""
    if not _is_rogue(pc):
        return []
    out: list[dict] = []
    for lvl in range(1, pc.get("level", 1) + 1):
        for name, desc in _ROGUE_AUTO.get(lvl, []):
            out.append(_feat(name, desc, lvl))
    return out
