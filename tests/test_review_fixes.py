"""Locks the A–D review fixes."""
from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.sim import factions


def _hero():
    state.upsert_pc({"id": "PC-h", "name": "Kaelrath", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "conditions": []})


# D — CONDITION_ADD must survive commas in the condition name
def test_condition_add_comma_in_name(fresh_db):
    _hero()
    mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD",
                                        args=["Kaelrath", "poisoned, weakened", "3"],
                                        raw="CONDITION_ADD: Kaelrath, poisoned, weakened, 3")])
    conds = state.get_pc("PC-h")["conditions"]
    assert conds == [{"name": "poisoned, weakened", "rounds": 3}]


def test_condition_add_plain(fresh_db):
    _hero()
    mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD", args=["Kaelrath", "prone"],
                                        raw="CONDITION_ADD: Kaelrath, prone")])
    assert state.get_pc("PC-h")["conditions"] == [{"name": "prone", "rounds": None}]


# B — faction resources must stay bounded no matter how long the sim runs
def test_faction_resources_stay_bounded(fresh_db):
    state.upsert_faction({"id": "F1", "name": "The Pale Hand", "resources": 38, "goal_tier": "dominance"})
    state.upsert_faction({"id": "F2", "name": "Ashers", "resources": 1, "goal_tier": "survival"})
    for _ in range(400):
        factions.tick()
    for fid in ("F1", "F2"):
        res = state.get_faction(fid)["resources"]
        assert factions.RES_MIN <= res <= factions.RES_MAX


# #1 — re-applying a condition refreshes duration, never stacks duplicates
def test_condition_add_dedupes(fresh_db):
    _hero()
    for rounds in ("3", "5", "2"):
        mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD", args=["Kaelrath", "Exhaustion", rounds],
                                            raw=f"CONDITION_ADD: Kaelrath, Exhaustion, {rounds}")])
    conds = state.get_pc("PC-h")["conditions"]
    assert conds == [{"name": "Exhaustion", "rounds": 2}]   # one entry, latest duration
