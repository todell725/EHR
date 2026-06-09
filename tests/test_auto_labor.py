"""Smart labor auto-allocation: food first, crafters when building, balanced when prosperous —
never a dumb even split, and the total always equals population."""

from backend.sim import kingdom


def _domain(**over):
    kingdom.found_domain("Testford", enable_economy=False)
    d = kingdom.get_domain()
    d.update({"population": 200, "morale": 4,
              "stockpiles": {"food": 2000, "lumber": 5000, "ore": 500},
              "projects": []})
    d.update(over)
    kingdom.set_domain(d)


def test_famine_prioritizes_farming(fresh_db):
    _domain(stockpiles={"food": 50, "lumber": 5000, "ore": 500})  # food < pop
    r = kingdom.auto_labor()
    lab = r["labor"]
    assert lab["farming"] == max(lab.values())          # farmers dominate
    assert lab["farming"] >= int(200 * 0.55)
    assert sum(lab.values()) == 200                     # exact total == population
    assert "famine" in r["rationale"].lower()


def test_building_boosts_crafters(fresh_db):
    _domain(projects=[{"key": "granary", "turns_left": 2}])  # actively building
    lab = kingdom.auto_labor()["labor"]
    assert lab["craft"] >= int(200 * 0.30)              # crafters pushed up
    assert sum(lab.values()) == 200


def test_prosperous_is_balanced_not_even(fresh_db):
    _domain()                                           # fed, not building
    lab = kingdom.auto_labor()["labor"]
    assert sum(lab.values()) == 200
    even = 200 // 4
    assert lab["farming"] != even or lab["military"] != even   # NOT a dumb even split
    assert lab["idle"] < lab["farming"]                # idle minimized vs farming
