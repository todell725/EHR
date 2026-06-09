"""EmberHeart homebrew ruleset — codified from the existing campaign corpus.

Derived from `Claudes-EmberHeart/docs/PARTY_STATE.json` and the `*_DB.json` idle
skill databases. The system is **5e-derived core** plus a **RuneScape-style idle
skill ladder**:

  * d20 ability checks: `d20 + ability_mod (+ proficiency if proficient)` vs a DC;
  * combat uses ability scores, AC, HP, initiative, conditions, death saves;
  * custom dice exist per-character (e.g. psionic power die, sneak-attack dice);
  * "idle skills" (mining, smithing, farming, slayer, ...) are leveled separately
    via accumulated XP, with task gates by `min_level`.

ASSUMPTIONS (flagged for review — all live in this file so they're easy to tune):
  A1. Ability modifier uses the standard 5e formula `(score - 10) // 2`.
  A2. Default proficiency bonus follows the 5e level table, BUT the corpus stores
      a per-character `proficiency_bonus` (Kaelrath = 3 at L20, non-standard), so a
      character's stored value always overrides the table.
  A3. Idle-skill XP uses the exact RuneScape XP curve (iconic, satisfying grind),
      capped at level 99. Corpus skill levels (e.g. mining 32) fit this range.
  A4. Character-level XP uses the 5e milestone thresholds by default. The corpus
      diverges (522,225 XP @ L20 vs 5e's 355,000), so character leveling is
      treated as GM-confirmed: XP accrues, level-up is suggested, not auto-applied.
  A5. Difficulty -> DC ladder is the 5e one (Very Easy 5 ... Nearly Impossible 30).
"""

from __future__ import annotations

from functools import lru_cache

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

IDLE_SKILLS = [
    "mining", "smithing", "woodcutting", "timbercraft", "fishing", "hunting",
    "cooking", "crafting", "slayer", "farming", "herbalism", "survival",
    "stonecraft", "influence", "tradecraft",
]

MAX_SKILL_LEVEL = 99  # A3

# A5 — 5e difficulty ladder.
DIFFICULTY_DC = {
    "trivial": 5, "very easy": 5, "easy": 10, "medium": 15, "moderate": 15,
    "hard": 20, "very hard": 25, "nearly impossible": 30,
}


# ------------------------------------------------------------------ A1: ability
def ability_mod(score: int | None) -> int:
    if score is None:
        return 0
    return (int(score) - 10) // 2


# -------------------------------------------------------------- A2: proficiency
def proficiency_bonus(level: int) -> int:
    """Standard 5e proficiency by level (overridden by a stored per-PC value)."""
    return 2 + max(0, (max(1, int(level)) - 1)) // 4


# ------------------------------------------------------- A3: idle-skill XP curve
@lru_cache(maxsize=1)
def _skill_xp_table() -> list[int]:
    """Cumulative XP needed to *reach* each level (RuneScape formula)."""
    table = [0, 0]  # index by level; level 1 = 0 xp
    points = 0
    for lvl in range(1, MAX_SKILL_LEVEL):
        points += int(lvl + 300 * (2 ** (lvl / 7.0)))
        table.append(points // 4)
    return table  # len == MAX_SKILL_LEVEL + 1


def skill_level_for_xp(xp: int) -> int:
    table = _skill_xp_table()
    lvl = 1
    for level, needed in enumerate(table):
        if xp >= needed:
            lvl = level
        else:
            break
    return min(lvl, MAX_SKILL_LEVEL)


def skill_xp_for_level(level: int) -> int:
    level = max(1, min(int(level), MAX_SKILL_LEVEL))
    return _skill_xp_table()[level]


# ---------------------------------------------------- A4: character-level XP (5e)
CHAR_LEVEL_XP = [
    0, 0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000,
    305000, 355000,
]  # index = level (1..20)


def char_level_for_xp(xp: int) -> int:
    lvl = 1
    for level, needed in enumerate(CHAR_LEVEL_XP):
        if level >= 1 and xp >= needed:
            lvl = level
    return min(lvl, 20)


# ------------------------------------------------------------------- difficulty
def dc_for_difficulty(name: str, default: int = 15) -> int:
    return DIFFICULTY_DC.get(name.strip().lower(), default)


# --------------------------------------------------------------- skill checking
def passive_skill(level: int) -> int:
    """A passive/threshold value for an idle skill, à la 5e passive scores."""
    return 10 + level
