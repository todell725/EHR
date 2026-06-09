"""Injected beats apply state through the trust boundary — no narrative/state split-brain."""
from backend.api.play import apply_inject_mechanics
from backend.core import state


def _hero(inv=None):
    state.upsert_pc({"id": "PC-h", "name": "Kaelrath", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "inventory": inv or []})


def test_inject_applies_real_state_through_boundary(fresh_db):
    _hero([{"item": "Gold", "qty": 10}])
    display = apply_inject_mechanics(["ITEM_ADD: Kaelrath, Gold, 5"])
    assert state.get_pc("PC-h")["inventory"] == [{"item": "Gold", "qty": 15}]   # state really moved
    assert any("Gold" in d for d in display)                                    # and it's reported


def test_inject_typo_is_surfaced_not_silently_wrong(fresh_db):
    _hero()
    # a malformed authored tag must be visible (rejected/noted), not a silent desync
    display = apply_inject_mechanics(["HP_CHANGE: Kaelrath"])      # missing the delta
    assert state.get_pc("PC-h")["hp"] == 10                       # nothing silently changed
    assert any("note" in d.lower() or "reject" in d.lower() for d in display)
