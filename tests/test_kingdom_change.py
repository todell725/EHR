from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.sim import kingdom


def _found(fresh_db):
    kingdom.found_domain("Testford", enable_economy=False)
    d = kingdom.get_domain()
    d.update({"morale": 3, "treasury": 100, "military": 10,
              "stockpiles": {"food": 200, "lumber": 50}})
    kingdom.set_domain(d)


def test_kingdom_change_top_stats(fresh_db):
    _found(fresh_db)
    mechanics.apply_mechanics([
        Mechanic(tag="KINGDOM_CHANGE", args=["morale", "+1"], raw="KINGDOM_CHANGE: morale, +1"),
        Mechanic(tag="KINGDOM_CHANGE", args=["treasury", "-30"], raw="KINGDOM_CHANGE: treasury, -30"),
        Mechanic(tag="REALM", args=["army", "+5"], raw="REALM: army, +5"),  # alias tag + stat
    ])
    d = kingdom.get_domain()
    assert d["morale"] == 4 and d["treasury"] == 70 and d["military"] == 15


def test_kingdom_change_morale_clamps_and_stockpiles(fresh_db):
    _found(fresh_db)
    mechanics.apply_mechanics([
        Mechanic(tag="KINGDOM_CHANGE", args=["morale", "+9"], raw="x"),     # clamp to 5
        Mechanic(tag="KINGDOM_CHANGE", args=["food", "+500"], raw="x"),     # stockpile
        Mechanic(tag="KINGDOM_CHANGE", args=["lumber", "-999"], raw="x"),   # clamp at 0
    ])
    d = kingdom.get_domain()
    assert d["morale"] == 5
    assert d["stockpiles"]["food"] == 700 and d["stockpiles"]["lumber"] == 0
