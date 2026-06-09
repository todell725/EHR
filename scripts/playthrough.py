"""Automated playthrough harness — the reliability proof for issue #1.

Drives N canned actions through the real DM orchestrator against a live Ollama, then
reports on contract adherence and state integrity. Use this after any prompt/model
change to catch drift before it bites you in a real session.

    ./.venv/bin/python scripts/playthrough.py --turns 15
    NARRATION_MODEL=gemma4:e4b ./.venv/bin/python scripts/playthrough.py --turns 30

Exits non-zero if the parse-ok rate or invariant checks fall below threshold.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from backend.core import db, state
from backend.llm.client import get_llm
from backend.rules import homebrew

ACTIONS = [
    "I look around the frozen camp and take stock of who survived.",
    "I approach the nearest stranger and ask their name.",
    "I search the abandoned supply tent for anything useful.",
    "I try to mend a gap in the palisade before nightfall.",
    "I ask about rumors of what stalks the northern woods.",
    "I share my rations with a starving child by the fire.",
    "I scout the treeline at the edge of camp, staying low.",
    "I challenge the man who's been eyeing my pack.",
    "I draw my dagger when I hear a snarl from the dark.",
    "I attack the thing lunging out of the shadows!",
    "I try to rally the others to stand and fight.",
    "I bind my wounds and rest by the embers.",
    "I bargain with a passing trader for a warmer cloak.",
    "I investigate strange tracks circling the camp.",
    "I climb the watchtower to see what lies beyond the marsh.",
    "I confront the sentry about the abandoned fire.",
    "I offer to lead a hunt for food at first light.",
    "I press deeper into the ruins beneath the camp.",
    "I demand answers from the hooded figure at the gate.",
    "I make camp and ask the others to tell me their stories.",
]


def _seed():
    db.init_db()
    db.upsert("locations", {"id": "LOC-start", "name": "The Frontier Camp",
                            "region": "The Ashen Marches", "discovered": 1,
                            "description": "A cold frontier camp."})
    state.update_world(location_id="LOC-start", arc_phase="origins")
    ab = {"str": 13, "dex": 15, "con": 14, "int": 10, "wis": 12, "cha": 11}
    hp = 8 + homebrew.ability_mod(ab["con"])
    state.upsert_pc({"id": "PC-01", "name": "Ash Vorn", "race": "Human", "class": "Scout",
                     "level": 1, "hp": hp, "max_hp": hp, "ac": 12, "abilities": ab,
                     "custom_dice": {"proficiency_bonus": 2}})


def _invariants() -> list[str]:
    problems = []
    for pc in state.list_pcs():
        if not (0 <= pc["hp"] <= pc["max_hp"]):
            problems.append(f"{pc['name']} HP out of bounds: {pc['hp']}/{pc['max_hp']}")
        for item in pc.get("inventory", []):
            if item.get("qty", 1) < 0:
                problems.append(f"{pc['name']} negative qty of {item.get('item')}")
    return problems


async def main(turns: int) -> int:
    from backend.dm import orchestrator

    if not await get_llm().health_check():
        print("Ollama not reachable — skipping playthrough.")
        return 0

    _seed()
    ok = 0
    rejected_total = 0
    rejected_samples: list[str] = []
    exceptions = 0
    violations: list[str] = []

    for i in range(turns):
        action = ACTIONS[i % len(ACTIONS)]
        try:
            res = await orchestrator.take_turn(action, pc_id="PC-01")
        except Exception as exc:  # noqa: BLE001
            exceptions += 1
            print(f"  turn {i+1}: EXCEPTION {exc}")
            continue
        if res.get("type") == "error":
            exceptions += 1
            print(f"  turn {i+1}: ERROR {res['message']}")
            continue
        has_narr = bool(res.get("narrative", "").strip())
        ok += 1 if has_narr else 0
        rejected_total += len(res.get("rejected", []))
        rejected_samples += res.get("rejected", [])
        bad = _invariants()
        violations += bad
        flag = "" if has_narr and not bad else "  <-- CHECK"
        print(f"  turn {i+1:2d}: narr={'Y' if has_narr else 'N'} "
              f"applied={len(res.get('applied',[]))} rejected={len(res.get('rejected',[]))} "
              f"rolls={len(res.get('rolls',[]))}{flag}")

    rate = ok / turns if turns else 0
    final_scene = state.get_world().get("scene", "")
    last_beats = state.recent_chronicle(limit=3)
    await get_llm().close()
    print("\n=== PLAYTHROUGH REPORT ===")
    print(f"turns:               {turns}")
    print(f"narrative-ok rate:   {rate:.0%}")
    print(f"rejected mechanics:  {rejected_total}")
    print(f"exceptions:          {exceptions}")
    print(f"invariant violations:{len(violations)}")
    print(f"final CURRENT SCENE: {final_scene[:120] or '(never set — drift risk)'}")
    if rejected_samples:
        print("rejection reasons:")
        for r in rejected_samples[:8]:
            print("   ⨯", r[:110])
    print("last chronicle beats (eyeball for consistency):")
    for b in last_beats:
        print("   -", b["content"][:110])
    for v in violations[:10]:
        print("   -", v)

    healthy = rate >= 0.8 and exceptions == 0 and not violations
    print("RESULT:", "PASS ✅" if healthy else "NEEDS ATTENTION ⚠")
    return 0 if healthy else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=15)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.turns)))
