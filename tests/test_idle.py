import time

from backend.core import state
from backend.sim import idle


def _hero():
    state.upsert_pc({"id": "PC-1", "name": "Kael", "is_player": 1,
                     "skills": {"woodcutting": 1, "hunting": 1, "cooking": 1, "smithing": 1},
                     "skill_xp": {}})


def test_gathering_produces_materials_and_xp(fresh_db):
    _hero()
    idle.set_active("woodcutting")
    # rewind last_tick so a chunk of cycles is due
    idle._save_idle({"active": "woodcutting", "last_tick": time.time() - 60})
    r = idle.tick()
    assert r and r["cycles"] >= 8                 # 60s / 6s ~ 10 cycles
    assert idle.get_state()["materials"].get("wood", 0) >= 8
    assert state.get_pc("PC-1")["skill_xp"]["woodcutting"] > 0


def test_processing_is_gated_on_inputs(fresh_db):
    _hero()
    # cooking needs raw_meat + wood; with none, it stalls
    idle._save_idle({"active": "cooking", "last_tick": time.time() - 60})
    r = idle.tick()
    assert r and "stalled" in r                   # no meat/wood -> stalled, no output
    assert idle.get_state()["materials"].get("cooked_meal", 0) == 0

    # give it inputs; now it cooks (consuming them)
    idle._save_materials({"raw_meat": 5, "wood": 5})
    idle._save_idle({"active": "cooking", "last_tick": time.time() - 60})
    idle.tick()
    m = idle.get_state()["materials"]
    assert m.get("cooked_meal", 0) >= 1
    assert m.get("raw_meat", 0) < 5               # meat was consumed (0 is filtered from view)


def test_smithing_locked_until_level_5(fresh_db):
    _hero()  # smithing level 1
    acts = {a["name"]: a for a in idle.get_state()["activities"]}
    assert acts["smithing"]["unlocked"] is False  # needs level 5
    assert acts["woodcutting"]["unlocked"] is True
