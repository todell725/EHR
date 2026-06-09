"""Senior-dev regression: completed buildings must have LIVE ongoing effects in the
economy tick (the granary cap, workshop craft bonus, market income) — not dead keys."""

from backend.sim import economy, kingdom


def _domain(**over):
    kingdom.found_domain("Testford", enable_economy=False)
    d = kingdom.get_domain()
    d.update({"population": 100, "morale": 3, "treasury": 0,
              "labor": {"farming": 50, "military": 0, "craft": 50, "idle": 0},
              "stockpiles": {"food": 0, "ore": 0, "lumber": 0},
              "buildings": [], "projects": []})
    d.update(over)
    kingdom.set_domain(d)
    return d


def test_workshop_boosts_craft_and_market_pays(fresh_db):
    _domain()
    base = economy.tick()
    _domain(buildings=["shardwork", "hearth_hall"])
    boosted = economy.tick()
    assert boosted["ore"] > base["ore"]          # shardwork craft_bonus is live
    assert boosted["lumber"] > base["lumber"]
    assert boosted["treasury"] > base["treasury"]  # hearth_hall trade_income is live


def test_granary_raises_food_cap(fresh_db):
    _domain(stockpiles={"food": 5000})           # over-full so the cap is what bites
    assert economy.tick()["food"] == 600         # pop*6, no granary
    _domain(buildings=["grand_granaries"], stockpiles={"food": 5000})
    assert economy.tick()["food"] == 840         # pop*6 * 1.40, grand_granaries live


def test_supplies_now_produced(fresh_db):
    # supplies used to be a dead resource — the tick must now generate it
    _domain(stockpiles={"food": 0, "ore": 0, "lumber": 0, "supplies": 0})
    base = economy.tick()
    assert base["supplies"] > 0                 # craft labour alone makes some
    _domain(buildings=["weavers_guild", "tannery", "alchemists_den"],
            stockpiles={"food": 0, "ore": 0, "lumber": 0, "supplies": 0})
    withbldgs = economy.tick()
    assert withbldgs["supplies"] > base["supplies"]   # the manufacturing buildings add more


def test_growth_uses_housing_ceiling_not_throttle(fresh_db):
    # housing_cap is a real ceiling; growth runs at the natural ~1.5%/tick up to it
    _domain(population=10000, morale=5, stockpiles={"food": 999999},
            buildings=[])
    d = kingdom.get_domain(); d["housing_cap"] = 15000; kingdom.set_domain(d)
    after = economy.tick()
    assert after["population"] == 10000 + 10000 // 65    # ~+153, not throttled to 20
    # at the ceiling, growth stops
    _domain(population=15000, morale=5, stockpiles={"food": 999999})
    d = kingdom.get_domain(); d["housing_cap"] = 15000; kingdom.set_domain(d)
    assert economy.tick()["population"] == 15000


def test_proposed_building_is_buildable(fresh_db):
    # a building proposed in-story must appear in the catalog and be buildable
    from backend.dm import mechanics
    from backend.core.models import Mechanic
    kingdom.found_domain("Testford", enable_economy=False)
    d = kingdom.get_domain(); d.update({"treasury": 9999, "stockpiles": {"lumber": 9999, "ore": 9999}}); kingdom.set_domain(d)
    mechanics.apply_mechanics([Mechanic(tag="BUILDING_PROPOSE", args=["Sky-Watch Spire", "defense"],
                                        raw="BUILDING_PROPOSE: Sky-Watch Spire, defense")])
    cat = kingdom.all_buildings()
    key = next(k for k, v in cat.items() if v["label"] == "Sky-Watch Spire")
    assert cat[key]["category"] == "defense"
    assert key in kingdom.get_summary()["catalog"]          # shows in the dashboard
    assert kingdom.start_building(key)["ok"] is True        # and is actually buildable


def test_upgrade_replaces_base(fresh_db):
    kingdom.found_domain("Upville", enable_economy=False)
    d = kingdom.get_domain(); d.update({"treasury": 99999, "stockpiles": {"lumber": 99999, "ore": 99999}, "buildings": ["ring_housing"]}); kingdom.set_domain(d)
    kingdom.add_building("Grand Ring-Housing", key="grand_ring_housing", category="civilian",
                         upgrades_from="ring_housing", ongoing={"pop_cap_bonus": 600}, turns=1)
    assert kingdom.start_building("grand_ring_housing")["ok"] is True
    kingdom.tick_projects()
    built = kingdom.get_domain()["buildings"]
    assert "grand_ring_housing" in built and "ring_housing" not in built   # replaced


def test_crews_set_and_get(fresh_db):
    kingdom.found_domain("Crewton", enable_economy=False)
    kingdom.add_crew("Wall Crew", size=120, role="ring housing")
    kingdom.set_crews([{"name": "Wall Crew", "size": 200, "role": "ring housing"},
                       {"name": "Rangers", "size": 40, "role": "north watch"}])
    crews = kingdom.get_domain()["crews"]
    assert len(crews) == 2 and crews[0]["size"] == 200
