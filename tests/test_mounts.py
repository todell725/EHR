from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.memory import working


def test_mount_crud(fresh_db):
    state.upsert_mount({"id": "MNT-1", "name": "Cindermane", "kind": "horse",
                        "hp": 19, "max_hp": 19, "traits": ["ember-maned"]})
    m = state.get_mount("MNT-1")
    assert m["name"] == "Cindermane" and m["traits"] == ["ember-maned"]
    assert state.find_mount_by_name("cindermane")["id"] == "MNT-1"
    # soft-remove drops it from the active list
    state.upsert_mount({"id": "MNT-1", "status": "dead"})
    assert state.list_mounts() == []


def test_mount_tame_mechanic(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath", "is_player": 1, "hp": 10, "max_hp": 10, "ac": 10})
    res = mechanics.apply_mechanics([Mechanic(
        tag="TAME", args=["Cindermane", "horse", "ember-maned"], raw="TAME: Cindermane, horse, ember-maned")])
    assert any("Cindermane" in a for a in res["applied"])
    m = state.find_mount_by_name("Cindermane")
    assert m and m["owner_pc_id"] == "PC-1" and "ember-maned" in m["traits"]
    # no duplicate on a second tame of the same name
    mechanics.apply_mechanics([Mechanic(tag="MOUNT_TAME", args=["Cindermane"], raw="x")])
    assert len(state.list_mounts()) == 1


def test_mount_in_working_memory(fresh_db):
    state.upsert_mount({"id": "MNT-2", "name": "Cindermane", "kind": "horse", "hp": 19, "max_hp": 19,
                        "traits": ["ember-maned"], "active": 1})
    block = working.build_scene_block()
    assert "MOUNTS" in block and "Cindermane" in block
