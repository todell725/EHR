"""Dice engine — the *only* source of randomness in the system.

Per the design spec's hard rule: the LLM never rolls dice (it biases results
toward drama). When the DM emits a `ROLL_REQUEST`/`SAVE_REQUEST`, the engine rolls
here and injects a deterministic `ROLL_RESULT` into the next turn.

Supported expression grammar (case-insensitive), terms joined by `+`/`-`:
    NdM        e.g. 2d6, 1d20      (N dice of M sides)
    dM         e.g. d20            (shorthand for 1dM)
    <int>      e.g. 5, -1          (flat modifier)
    <ability>  STR DEX CON INT WIS CHA  (resolved to a PC's ability modifier)
    PROF       the PC's proficiency bonus

Advantage/disadvantage applies to a leading single d20 (5e-style).
"""

from __future__ import annotations

import random
import re
from typing import Literal

from backend.core.models import RollResult
from backend.rules import homebrew

_TERM = re.compile(r"(?P<sign>[+-])?\s*(?P<body>\d*d\d+|\d+|[a-zA-Z]+)", re.IGNORECASE)
_DICE = re.compile(r"(?P<n>\d*)d(?P<m>\d+)", re.IGNORECASE)

Adv = Literal["advantage", "disadvantage", None]

# 5e-style difficulty ladder used when a label implies a band but no DC is given.
DC_BY_DIFFICULTY = {
    "very easy": 5, "easy": 10, "medium": 15, "moderate": 15,
    "hard": 20, "very hard": 25, "nearly impossible": 30,
}


def _ability_mod_from_pc(token: str, pc: dict | None) -> int:
    token = token.upper()
    if pc is None:
        return 0
    if token == "PROF":
        # explicit per-PC proficiency wins; else derive from level
        prof = (pc.get("custom_dice") or {}).get("proficiency_bonus")
        return int(prof) if prof is not None else homebrew.proficiency_bonus(pc.get("level", 1))
    if token in homebrew.ABILITIES:
        score = (pc.get("abilities") or {}).get(token.lower())
        return homebrew.ability_mod(score) if score is not None else 0
    return 0


def roll_expression(
    expression: str,
    *,
    pc: dict | None = None,
    advantage: Adv = None,
    dc: int | None = None,
    label: str = "",
) -> RollResult:
    """Roll a dice expression and (optionally) resolve success against a DC."""
    rolls: list[int] = []
    modifier = 0
    first_d20_natural: int | None = None

    for m in _TERM.finditer(expression.replace(" ", "")):
        body = m.group("body")
        sign = -1 if m.group("sign") == "-" else 1
        dice_m = _DICE.fullmatch(body)
        if dice_m:
            n = int(dice_m.group("n") or 1)
            size = int(dice_m.group("m"))
            for i in range(n):
                if size == 20 and advantage and first_d20_natural is None and n == 1:
                    a, b = random.randint(1, 20), random.randint(1, 20)
                    nat = max(a, b) if advantage == "advantage" else min(a, b)
                else:
                    nat = random.randint(1, size)
                if size == 20 and first_d20_natural is None:
                    first_d20_natural = nat
                rolls.append(sign * nat)
        elif body.isdigit():
            modifier += sign * int(body)
        else:  # ability / PROF token
            modifier += sign * _ability_mod_from_pc(body, pc)

    total = sum(rolls) + modifier

    outcome: str | None = None
    if first_d20_natural == 20:
        outcome = "CRIT"
    elif first_d20_natural == 1:
        outcome = "FUMBLE"
    elif dc is not None:
        outcome = "SUCCESS" if total >= dc else "FAILURE"

    return RollResult(
        expression=expression,
        label=label or expression,
        rolls=[abs(r) for r in rolls],
        modifier=modifier,
        total=total,
        outcome=outcome,
        dc=dc,
    )


def dc_for(difficulty_or_label: str, default: int = 15) -> int:
    return DC_BY_DIFFICULTY.get(difficulty_or_label.strip().lower(), default)


def format_result(r: RollResult) -> str:
    """Render the `ROLL_RESULT:` line injected back into the DM prompt."""
    dice_part = " + ".join(str(x) for x in r.rolls) if r.rolls else "0"
    mod = f" {'+' if r.modifier >= 0 else '-'} {abs(r.modifier)}" if r.modifier else ""
    head = f"ROLL_RESULT: {r.label}, rolled [{dice_part}]{mod} = {r.total}"
    if r.dc is not None:
        head += f" vs DC {r.dc}"
    if r.outcome:
        head += f" -> {r.outcome}"
    return head
