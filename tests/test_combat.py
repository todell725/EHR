import random

from backend.core import state
from backend.dm.mechanics import _parse_enemy
from backend.sim import combat


def _mk_pc(pid, name, hp, ac, dex=14):
    state.upsert_pc({"id": pid, "name": name, "hp": hp, "max_hp": hp, "ac": ac,
                     "abilities": {"dex": dex, "con": 12}, "status": "alive"})


def test_parse_enemy_count_and_stats():
    enemies = _parse_enemy("Frost Wolf x2 hp7 ac13 atk5 ai:tactical")
    assert len(enemies) == 2
    assert enemies[0]["name"] == "Frost Wolf 1"
    assert enemies[0]["hp"] == 7 and enemies[0]["ac"] == 13
    assert enemies[0]["attack_bonus"] == 5 and enemies[0]["ai"] == "tactical"


def test_initiative_and_participants(fresh_db):
    random.seed(7)
    _mk_pc("PC-1", "Bram", 20, 16)
    enc = combat.start_combat([{"name": "Rat", "hp": 3, "ac": 10, "ai": "berserker"}])
    sides = {p["side"] for p in enc["participants"]}
    assert sides == {"party", "enemy"}
    assert enc["round"] == 1


def test_player_kills_enemy_ends_in_victory(fresh_db):
    random.seed(1)
    _mk_pc("PC-1", "Bram", 20, 18)
    combat.start_combat([{"name": "Rat", "hp": 3, "ac": 5, "ai": "berserker"}])
    # simulate the DM declaring the killing blow
    assert combat.set_enemy_hp("Rat", 0) is True
    res = combat.end_player_turn()
    assert res["ended"] is True
    assert res["victor"] == "party"
    assert combat.status() is None  # encounter closed


def test_fragile_pc_can_die_to_strong_enemy(fresh_db):
    random.seed(3)
    _mk_pc("PC-1", "Glass", 1, 1)  # basically guaranteed to drop
    combat.start_combat([
        {"name": "Ogre", "hp": 30, "ac": 18, "attack_bonus": 12, "damage": "2d8+5", "ai": "berserker"}
    ])
    ended = False
    for _ in range(20):  # the PC acts, then we resolve enemies each "turn"
        res = combat.end_player_turn()
        if res.get("ended"):
            ended = True
            assert res["victor"] == "enemy"
            break
    assert ended


def test_condition_ticks_down():
    parts = [{"name": "Bram", "conditions": [{"name": "Restrained", "rounds": 1}]}]
    log: list[str] = []
    combat._tick_conditions(parts, log)
    assert parts[0]["conditions"] == []
    assert any("no longer Restrained" in m for m in log)
