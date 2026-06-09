"""Locks the codex-review fixes (2026-06-09): undo/feed coherence, inject beat
post-processing, partial labor merges, atomic material spends, explicit-but-unknown
PC targets, and /play/action going through the broker."""

import asyncio
import time

from backend.api import play as play_api
from backend.core import state
from backend.core.models import Mechanic, PlayAction
from backend.dm import broker as brokermod
from backend.dm import mechanics, orchestrator
from backend.sim import idle, kingdom


def _hero(name="Kaelrath Emberhide"):
    state.upsert_pc({"id": "PC-h", "name": name, "is_player": 1, "hp": 20, "max_hp": 20,
                     "ac": 10, "conditions": [], "inventory": []})


# ----- 1 — undo must roll the broker feed back with the DB --------------------

def test_restore_feed_clears_memory_when_db_has_none(fresh_db):
    tb = brokermod.TurnBroker()
    tb.recent.append({"seq": 5, "status": "done", "action": "x", "events": []})
    tb.current = tb.recent[-1]
    tb.restore_feed()   # fresh DB has no feed_recent -> the undone beat must not linger
    assert list(tb.recent) == [] and tb.current is None


def test_undo_rejected_while_turn_running(fresh_db, monkeypatch):
    monkeypatch.setattr(play_api.broker, "current",
                        {"seq": 1, "status": "running", "action": "x",
                         "events": [], "started_at": time.time()})
    res = play_api.session_undo()
    assert res["ok"] is False and "running" in res["detail"]


# ----- 2 — injected mechanics get the post-processing that makes sense --------

def test_inject_time_advance_actually_moves_calendar(fresh_db):
    _hero()
    day0 = state.get_world().get("day", 1)
    out = play_api.apply_inject_mechanics(["TIME_ADVANCE: 2, days"])
    assert state.get_world().get("day") == day0 + 2
    assert any("time advances" in s for s in out)


def test_inject_combat_tags_are_called_out(fresh_db):
    _hero()
    out = play_api.apply_inject_mechanics(["COMBAT_START: bandit ambush"])
    assert any("combat tags do nothing" in s for s in out)


# ----- 3 — a partial labor update merges instead of replacing -----------------

def test_set_labor_merges_partial_update(fresh_db):
    kingdom.found_domain("EmberHeart")
    before = dict(kingdom.get_domain()["labor"])
    kingdom.set_labor({"farming": 10})
    after = kingdom.get_domain()["labor"]
    assert after["farming"] == 10
    for k in before:
        if k != "farming":
            assert after[k] == before[k]   # untouched categories survive


# ----- 4 — material spends are atomic; no double credit -----------------------

def test_take_material_never_overdraws(fresh_db):
    state.set_materials({"wood": 100})
    assert state.take_material("wood", 60) == 60
    assert state.take_material("wood", 60) == 40
    assert state.take_material("wood", 60) == 0
    assert state.get_materials().get("wood", 0) == 0


def test_invest_credits_only_what_was_taken(fresh_db):
    kingdom.found_domain("EmberHeart")
    state.set_materials({"wood": 50})
    base = kingdom.get_domain()["stockpiles"].get("lumber", 0)
    r1 = kingdom.invest_material("wood", 50)
    r2 = kingdom.invest_material("wood", 50)
    assert r1["ok"] is True and r2["ok"] is False
    assert kingdom.get_domain()["stockpiles"]["lumber"] == base + 50


def test_idle_deposit_cannot_double_spend(fresh_db):
    _hero()
    state.set_materials({"wood": 30})
    r1 = idle.deposit_to_inventory("wood", 30)
    r2 = idle.deposit_to_inventory("wood", 30)
    assert r1["ok"] is True and r2["ok"] is False
    inv = state.get_pc("PC-h")["inventory"]
    assert sum(i["qty"] for i in inv if i["item"].lower() == "wood") == 30


# ----- 5 — explicit unknown PC targets are noted, never the hero --------------

def test_hp_change_unknown_target_noted_not_hero(fresh_db):
    _hero()
    res = mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=["Kryoss", "-5"],
                                              raw="HP_CHANGE: Kryoss, -5")])
    assert state.get_pc("PC-h")["hp"] == 20            # the hero did NOT take the hit
    assert any("Kryoss" in n for n in res["notes"])


def test_condition_add_unknown_target_noted(fresh_db):
    _hero()
    res = mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD", args=["Kryoss", "frozen"],
                                              raw="CONDITION_ADD: Kryoss, frozen")])
    assert state.get_pc("PC-h")["conditions"] == []
    assert any("Kryoss" in n for n in res["notes"])


def test_find_pc_partial_first_name_still_matches(fresh_db):
    _hero("Kaelrath Emberhide")
    mechanics.apply_mechanics([Mechanic(tag="HP_CHANGE", args=["Kaelrath", "-5"],
                                        raw="HP_CHANGE: Kaelrath, -5")])
    assert state.get_pc("PC-h")["hp"] == 15            # "Kaelrath" finds the full name


def test_xp_grant_party_keyword_hits_everyone(fresh_db):
    _hero()
    state.upsert_pc({"id": "PC-t", "name": "Talmarr", "is_player": 0,
                     "hp": 10, "max_hp": 10, "ac": 10})
    mechanics.apply_mechanics([Mechanic(tag="XP_GRANT", args=["party", "100"],
                                        raw="XP_GRANT: party, 100")])
    assert state.get_pc("PC-h")["xp"] >= 100
    assert state.get_pc("PC-t")["xp"] >= 100


# ----- 6 — /play/action runs through the broker --------------------------------

async def _fake_stream(action, pc_id=None):
    yield {"type": "start", "turn": 1}
    yield {"type": "result", "turn": 1, "narrative": "You kneel.",
           "suggestions": [], "applied": [], "rolls": []}


def test_play_action_routes_through_broker(fresh_db, monkeypatch):
    monkeypatch.setattr(orchestrator, "stream_turn", _fake_stream)
    tb = brokermod.TurnBroker()
    monkeypatch.setattr(play_api, "broker", tb)

    res = asyncio.run(play_api.play_action(PlayAction(text="kneel")))
    assert res["narrative"] == "You kneel."
    assert tb.recent and tb.recent[-1]["status"] == "done"   # the beat is in the feed


def test_play_action_rejected_while_turn_running(fresh_db, monkeypatch):
    tb = brokermod.TurnBroker()
    tb.current = {"seq": 1, "status": "running", "action": "x",
                  "events": [], "started_at": time.time()}
    monkeypatch.setattr(play_api, "broker", tb)

    res = asyncio.run(play_api.play_action(PlayAction(text="second")))
    assert res["ok"] is False
