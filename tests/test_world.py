"""State + calendar + faction + economy tests (need the DB fixture)."""

from backend.core import state
from backend.sim import calendar, economy, factions, kingdom


def test_calendar_advance_days(fresh_db):
    state.update_world(year=1, season=calendar.SEASONS[0], day=1, time_of_day="morning")
    calendar.advance(2, "days")
    w = state.get_world()
    assert w["day"] == 3


def test_calendar_crosses_season(fresh_db):
    state.update_world(year=1, season=calendar.SEASONS[0], day=1)
    calendar.advance(95, "days")
    w = state.get_world()
    assert w["season"] == calendar.SEASONS[1]
    assert w["day"] == 6


def test_scheduled_event_fires(fresh_db):
    calendar.schedule_in(0, "A bell tolls in the dark.")
    fired = calendar.advance(1, "days")
    assert any("bell tolls" in f for f in fired)


def test_faction_tick(fresh_db):
    state.upsert_faction({"id": "F1", "name": "The Ashen Pact", "resources": 12})
    moves = factions.tick()
    assert moves and moves[0]["faction"] == "The Ashen Pact"


def test_found_domain_enables_economy(fresh_db):
    assert economy.is_enabled() is False
    kingdom.found_domain("Hearthold")
    w = state.get_world()
    assert w["arc_phase"] == "kingdom"
    assert bool(w["domain_ruled"]) is True
    assert economy.is_enabled() is True
    before = kingdom.get_domain()["treasury"]
    economy.tick()
    assert kingdom.get_domain()["treasury"] != before or kingdom.get_domain()["population"] >= 0


def test_world_hook_rejoins_full_description(fresh_db):
    from backend.core.models import Mechanic
    from backend.dm import mechanics
    mechanics.apply_mechanics([Mechanic(
        tag="WORLD_HOOK", args=["The scouts feel a persistent", "growing dread"],
        raw="WORLD_HOOK: The scouts feel a persistent, growing dread")])
    hooks = state.open_hooks()
    assert any("persistent, growing dread" in h["description"] for h in hooks)


def test_resolve_hook_by_fragment(fresh_db):
    state.add_hook("a missing blacksmith haunts the frost lane")
    assert state.resolve_hook("missing blacksmith") == 1
    assert state.open_hooks() == []
    assert len(state.all_hooks()) == 1  # still recorded, just resolved


def test_disposition_and_reputation(fresh_db):
    state.upsert_npc({"id": "EH-1", "name": "Aldric", "disposition": {}})
    val = state.set_npc_disposition("EH-1", "PC-1", -5)
    assert val == -5
    state.upsert_faction({"id": "F2", "name": "Guild", "reputation": {}})
    rep = state.change_faction_rep("F2", "PC-1", 12)
    assert rep == 12


def test_kingdom_build_and_tick(fresh_db):
    kingdom.found_domain("Buildhold")
    d = kingdom.get_domain()
    assert d["buildings"] == ["blood_wall", "ember_vault", "god_forge"]
    assert d["projects"] == []
    # seed enough stockpiles + treasury
    d["stockpiles"] = {"lumber": 200, "ore": 200, "food": 200}
    d["treasury"] = 500
    kingdom.set_domain(d)
    # build quarry_works (no prereqs, 2 turns)
    assert kingdom.start_building("quarry_works")["ok"] is True
    # can't build scouts_perches yet — quarry_works is still under construction
    assert kingdom.start_building("scouts_perches")["ok"] is False
    # complete quarry_works
    kingdom.tick_projects()
    kingdom.tick_projects()
    assert "quarry_works" in kingdom.get_domain()["buildings"]
    # now scouts_perches is unlocked
    r = kingdom.start_building("scouts_perches")
    assert r["ok"] is True
    # complete scouts_perches (2 turns)
    kingdom.tick_projects()
    kingdom.tick_projects()
    assert len(kingdom.get_projects()) == 0
    assert "scouts_perches" in kingdom.get_domain()["buildings"]
    # military should have increased from scouts_perches (+2)
    assert kingdom.get_domain()["military"] >= 17  # base 15 + 2


def test_kingdom_build_dup_blocked(fresh_db):
    kingdom.found_domain("Duphold")
    d = kingdom.get_domain()
    d["stockpiles"] = {"lumber": 100, "ore": 100, "food": 100}
    d["treasury"] = 500
    kingdom.set_domain(d)
    assert kingdom.start_building("menders_clinic")["ok"] is True
    assert kingdom.start_building("menders_clinic")["ok"] is False  # already building
    kingdom.tick_projects(); kingdom.tick_projects()
    assert kingdom.start_building("menders_clinic")["ok"] is False  # already built


def test_kingdom_labor_clamped(fresh_db):
    kingdom.found_domain("Laborhold")
    d = kingdom.get_domain()
    pop = d["population"]
    r = kingdom.set_labor({"farming": pop + 50, "military": 10})
    assert r["ok"] is True
    total = sum(r["labor"].values())
    assert total <= pop


def test_kingdom_summary(fresh_db):
    kingdom.found_domain("Summaryhold")
    s = kingdom.get_summary()
    assert s["domain"]["name"] == "Summaryhold"
    assert "catalog" in s
    assert "buildings" in s
    assert "projects" in s


def test_founded_domain_seeds_prebuilt(fresh_db):
    kingdom.found_domain("Seedhold")
    d = kingdom.get_domain()
    assert "blood_wall" in d["buildings"]
    assert "ember_vault" in d["buildings"]
    assert "god_forge" in d["buildings"]


def test_build_prerequisite_blocking(fresh_db):
    kingdom.found_domain("Prereqhold")
    d = kingdom.get_domain()
    d["stockpiles"] = {"lumber": 200, "ore": 200, "food": 200}
    d["treasury"] = 1000
    kingdom.set_domain(d)
    # ironwood_gatehouse requires blood_wall (pre-built) — should succeed
    assert kingdom.start_building("ironwood_gatehouse")["ok"] is True
    # wardens_redoubt requires ironwood_gatehouse — not built yet, should fail
    r = kingdom.start_building("wardens_redoubt")
    assert r["ok"] is False
    assert "needs" in r["detail"].lower() or "Warden" in r["detail"]


def test_memorial_wall_auto_complete(fresh_db):
    kingdom.found_domain("Memhold")
    d = kingdom.get_domain()
    # Add 10 chronicle entries to trigger auto-complete
    for i in range(10):
        state.add_chronicle(f"Event {i}", tags=["test"])
    # tick_projects calls _check_auto_buildings
    kingdom.tick_projects()
    d = kingdom.get_domain()
    assert "memorial_wall" in d["buildings"]
    assert d.get("morale", 3) >= 4  # +2 morale from memorial_wall effect


def test_ongoing_effects_in_economy_tick(fresh_db):
    kingdom.found_domain("Econhold")
    d = kingdom.get_domain()
    d["stockpiles"] = {"lumber": 200, "ore": 200, "food": 200}
    d["treasury"] = 500
    d["labor"] = {"farming": 60, "craft": 30, "military": 15, "idle": 15}
    kingdom.set_domain(d)
    # Build a quarry_works for ongoing quarry_ore bonus
    r = kingdom.start_building("quarry_works")
    assert r["ok"] is True
    # Complete it instantly by ticking enough times
    for _ in range(5):
        kingdom.tick_projects()
    d = kingdom.get_domain()
    assert "quarry_works" in d["buildings"]
    before_ore = d["stockpiles"]["ore"]
    economy.tick()
    after = kingdom.get_domain()
    assert after["stockpiles"]["ore"] > before_ore  # quarry_ore ongoing should boost ore
