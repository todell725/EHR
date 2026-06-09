from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.sim import idle


def test_normalize_and_adjust(fresh_db):
    assert state.normalize_material("Logs") == "wood"
    assert state.normalize_material("meat") == "raw_meat"
    assert state.normalize_material("plant fiber") == "plant_fiber"
    assert state.adjust_material("logs", 100) == 100      # alias folds into wood
    assert state.adjust_material("wood", 50) == 150
    assert state.adjust_material("wood", -999) == 0       # clamps, drops empty
    assert "wood" not in state.get_materials()


def test_material_mechanics(fresh_db):
    state.adjust_material("wood", 500)
    res = mechanics.apply_mechanics([
        Mechanic(tag="MATERIAL_SPEND", args=["wood", "200"], raw="MATERIAL_SPEND: wood, 200"),
        Mechanic(tag="GATHER", args=["raw_meat", "10"], raw="GATHER: raw_meat, 10"),  # alias
    ])
    assert state.get_materials()["wood"] == 300
    assert state.get_materials()["raw_meat"] == 10
    assert any("wood" in a for a in res["applied"])


def test_deposit_to_pack(fresh_db):
    state.upsert_pc({"id": "PC-h", "name": "Hero", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "inventory": []})
    state.adjust_material("wood", 10000)
    out = idle.deposit_to_inventory("logs", 4000)        # alias -> wood
    assert out["ok"] is True and out["deposited"] == 4000
    assert state.get_materials()["wood"] == 6000
    hero = state.get_pc("PC-h")
    assert any(i["item"] == "Wood" and i["qty"] == 4000 for i in hero["inventory"])
