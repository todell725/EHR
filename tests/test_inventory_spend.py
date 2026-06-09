from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics


def _hero(inv):
    state.upsert_pc({"id": "PC-h", "name": "Kaelrath", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "inventory": inv})


def test_item_remove_depletes_by_qty(fresh_db):
    _hero([{"item": "Wood", "qty": 500}])
    mechanics.apply_mechanics([Mechanic(tag="ITEM_REMOVE", args=["Kaelrath", "Wood", "200"],
                                        raw="ITEM_REMOVE: Kaelrath, Wood, 200")])
    inv = state.get_pc("PC-h")["inventory"]
    assert inv == [{"item": "Wood", "qty": 300}]


def test_item_remove_fuzzy_match(fresh_db):
    # DM says 'moonveil' but the stack is 'Moonveil stalks' — must still deplete, not no-op
    _hero([{"item": "Moonveil stalks", "qty": 3}])
    mechanics.apply_mechanics([Mechanic(tag="ITEM_REMOVE", args=["moonveil"],
                                        raw="ITEM_REMOVE: moonveil")])
    inv = state.get_pc("PC-h")["inventory"]
    assert inv == [{"item": "Moonveil stalks", "qty": 2}]


def test_item_remove_no_pc_token(fresh_db):
    # no character named -> defaults to hero, all args are the item
    _hero([{"item": "Wood", "qty": 100}])
    mechanics.apply_mechanics([Mechanic(tag="ITEM_REMOVE", args=["Wood", "100"],
                                        raw="ITEM_REMOVE: Wood, 100")])
    assert state.get_pc("PC-h")["inventory"] == []     # whole stack gone


def test_item_add_merges_stack(fresh_db):
    _hero([{"item": "Wood", "qty": 100}])
    mechanics.apply_mechanics([Mechanic(tag="ITEM_ADD", args=["Kaelrath", "Wood", "50"],
                                        raw="ITEM_ADD: Kaelrath, Wood, 50")])
    assert state.get_pc("PC-h")["inventory"] == [{"item": "Wood", "qty": 150}]
