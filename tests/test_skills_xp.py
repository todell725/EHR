import random

from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.sim import combat


def test_skill_xp_levels_idle_skill(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kael", "skills": {"smithing": 5}, "skill_xp": {}})
    r = state.grant_skill_xp("PC-1", "smithing", 5000)
    assert r["level"] >= 5            # never goes backward from current level
    assert state.get_pc("PC-1")["skills"]["smithing"] == r["level"]
    assert state.get_pc("PC-1")["skill_xp"]["smithing"] >= 5000


def test_skill_xp_mechanic(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kael", "skills": {"hunting": 1}, "skill_xp": {}})
    res = mechanics.apply_mechanics(
        [Mechanic(tag="SKILL_XP", args=["hunting", "800"], raw="SKILL_XP: hunting, 800")],
        acting_pc_id="PC-1")
    assert res["rejected"] == [] and res["notes"] == []
    assert state.get_pc("PC-1")["skill_xp"]["hunting"] == 800


def test_skill_alias(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kael", "skills": {}, "skill_xp": {}})
    mechanics.apply_mechanics(
        [Mechanic(tag="TRAIN", args=["cooking", "200"], raw="TRAIN: cooking, 200")],
        acting_pc_id="PC-1")
    assert state.get_pc("PC-1")["skill_xp"]["cooking"] == 200  # TRAIN -> SKILL_XP


def test_combat_victory_awards_party_xp(fresh_db):
    random.seed(2)
    state.upsert_pc({"id": "PC-1", "name": "Bram", "hp": 20, "max_hp": 20, "ac": 18,
                     "xp": 0, "abilities": {"dex": 14}})
    combat.start_combat([{"name": "Rat", "hp": 6, "ac": 5, "ai": "berserker"}])
    combat.set_enemy_hp("Rat", 0)
    res = combat.end_player_turn()
    assert res["ended"] and res["victor"] == "party"
    assert state.get_pc("PC-1")["xp"] > 0            # the fight paid out XP
    assert any("XP from the battle" in line for line in res["log"])
