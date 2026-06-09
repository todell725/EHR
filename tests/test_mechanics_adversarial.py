"""Adversarial coverage for the trust boundary.

`mechanics.apply_mechanics` is the whole game's integrity guarantee: a small local
model WILL emit malformed, junk, mistyped, and occasionally hostile tags. The engine's
contract is that it *never crashes* and *never corrupts state* no matter what comes in —
bad input is noted/rejected, not applied. This suite throws garbage at the canonicalize →
lint → dispatch path and asserts the invariants hold.
"""

import pytest

from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics


def _hero(inv=None, hp=10, mx=10):
    state.upsert_pc({"id": "PC-h", "name": "Kaelrath", "is_player": 1, "hp": hp, "max_hp": mx,
                     "ac": 10, "inventory": inv if inv is not None else []})


# Each of these is the kind of thing a flaky 8B model actually emits. None may crash.
JUNK = [
    Mechanic(tag="HP_CHANGE", args=["Kaelrath", "+8 (Trust/Urgency)"], raw="HP_CHANGE: Kaelrath, +8 (Trust/Urgency)"),
    Mechanic(tag="HP_CHANGE", args=["Kaelrath", "lots"], raw="HP_CHANGE: Kaelrath, lots"),
    Mechanic(tag="HP_CHANGE", args=["Kaelrath", ""], raw="HP_CHANGE: Kaelrath,"),
    Mechanic(tag="HP_CHANGE", args=["Kaelrath"], raw="HP_CHANGE: Kaelrath"),
    Mechanic(tag="HP_CHANGE", args=[], raw="HP_CHANGE:"),
    Mechanic(tag="HP_CHANGE", args=["A Ghost Who Isn't Here", "-5"], raw="HP_CHANGE: A Ghost, -5"),
    Mechanic(tag="HP_CHANGE", args=["Kaelrath", "-99999999"], raw="HP_CHANGE: Kaelrath, -99999999"),
    Mechanic(tag="HP_CHANGE", args=["Kaelrath", "1e9"], raw="HP_CHANGE: Kaelrath, 1e9"),
    Mechanic(tag="ITEM_REMOVE", args=["Kaelrath", "Nonexistent Thing", "9999"], raw="ITEM_REMOVE: …"),
    Mechanic(tag="ITEM_ADD", args=["Kaelrath", "Gold", "-50"], raw="ITEM_ADD: Kaelrath, Gold, -50"),
    Mechanic(tag="ITEM_ADD", args=[], raw="ITEM_ADD:"),
    Mechanic(tag="ITEM_ADD", args=["Kaelrath", "a, curious, carved, bone fragment", "2"], raw="ITEM_ADD: …"),
    Mechanic(tag="XP_GRANT", args=["banana"], raw="XP_GRANT: banana"),
    Mechanic(tag="SKILL_XP", args=["Kaelrath"], raw="SKILL_XP: Kaelrath"),
    Mechanic(tag="KINGDOM_CHANGE", args=["treasury", "NaN"], raw="KINGDOM_CHANGE: treasury, NaN"),
    Mechanic(tag="KINGDOM_CHANGE", args=[], raw="KINGDOM_CHANGE:"),
    Mechanic(tag="CONDITION_ADD", args=[], raw="CONDITION_ADD:"),
    Mechanic(tag="MATERIAL_SPEND", args=["wood", "99999"], raw="MATERIAL_SPEND: wood, 99999"),
    Mechanic(tag="MOUNT_TAME", args=[], raw="MOUNT_TAME:"),
    Mechanic(tag="BUILDING_PROPOSE", args=[], raw="BUILDING_PROPOSE:"),
    Mechanic(tag="CREW_SET", args=[], raw="CREW_SET:"),
    Mechanic(tag="FLARGLE_WOBBET", args=["x", "y"], raw="FLARGLE_WOBBET: x, y"),      # unknown tag
    Mechanic(tag="", args=["x"], raw=": x"),                                          # empty tag
    Mechanic(tag="HP_CHANGE", args=["'; DROP TABLE player_characters;--", "-5"], raw="injection attempt"),
    Mechanic(tag="ITEM_REMOVE", args=["Kaelrath", "Gold", "not-a-number"], raw="ITEM_REMOVE: Kaelrath, Gold, x"),
]


@pytest.mark.parametrize("mech", JUNK, ids=lambda m: (m.tag or "EMPTY") + ":" + ",".join(m.args)[:18])
def test_junk_mechanic_never_crashes_or_corrupts(fresh_db, mech):
    _hero([{"item": "Gold", "qty": 10}])
    mechanics.apply_mechanics([mech])                       # must not raise
    pc = state.get_pc("PC-h")
    assert pc is not None                                   # table survived (no injection took)
    assert 0 <= pc["hp"] <= pc["max_hp"]                    # HP invariant holds
    assert all(it.get("qty", 0) >= 0 for it in pc["inventory"])   # no negative stacks


def test_entire_batch_of_junk_in_one_turn(fresh_db):
    _hero([{"item": "Gold", "qty": 10}])
    mechanics.apply_mechanics(JUNK)                         # the whole garbage pile at once
    pc = state.get_pc("PC-h")
    assert 0 <= pc["hp"] <= pc["max_hp"]
    assert all(it.get("qty", 0) >= 0 for it in pc["inventory"])


def test_hp_clamps_at_both_ends(fresh_db):
    _hero(hp=10, mx=10)
    mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=["Kaelrath", "+500"], raw="")])
    assert state.get_pc("PC-h")["hp"] == 10                 # can't exceed max
    mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=["Kaelrath", "-500"], raw="")])
    assert state.get_pc("PC-h")["hp"] == 0                  # can't go below floor


def test_coerce_int_pulls_number_from_noise(fresh_db):
    _hero(hp=5, mx=20)
    mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=["Kaelrath", "+8 (Trust/Urgency)"], raw="")])
    assert state.get_pc("PC-h")["hp"] == 13                 # extracted +8 from the noisy arg


def test_unknown_tag_is_noted_not_applied(fresh_db):
    _hero()
    res = mechanics.apply_mechanics([Mechanic(tag="FLARGLE_WOBBET", args=["x"], raw="FLARGLE_WOBBET: x")])
    assert any("FLARGLE" in n.upper() for n in res["notes"])   # captured as a note, not silently dropped
    assert not res["applied"]                                  # …and nothing was actually applied


def test_malformed_known_tag_is_rejected_or_ignored(fresh_db):
    # a recognized tag with no usable args must not crash or mutate state
    _hero()
    res = mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=[], raw="HP_CHANGE:")])
    assert res["rejected"] or not res["applied"]               # rejected (or at least not applied)
    assert state.get_pc("PC-h")["hp"] == 10                    # state untouched
