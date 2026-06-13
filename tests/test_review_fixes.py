"""Locks the A–D review fixes."""
from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.sim import factions


def _hero():
    state.upsert_pc({"id": "PC-h", "name": "Kaelrath", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "conditions": []})


# D — CONDITION_ADD must survive commas in the condition name
def test_condition_add_comma_in_name(fresh_db):
    _hero()
    mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD",
                                        args=["Kaelrath", "poisoned, weakened", "3"],
                                        raw="CONDITION_ADD: Kaelrath, poisoned, weakened, 3")])
    conds = state.get_pc("PC-h")["conditions"]
    assert conds == [{"name": "poisoned, weakened", "rounds": 3}]


def test_condition_add_plain(fresh_db):
    _hero()
    mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD", args=["Kaelrath", "prone"],
                                        raw="CONDITION_ADD: Kaelrath, prone")])
    assert state.get_pc("PC-h")["conditions"] == [{"name": "prone", "rounds": None}]


# B — faction resources must stay bounded no matter how long the sim runs
def test_faction_resources_stay_bounded(fresh_db):
    state.upsert_faction({"id": "F1", "name": "The Pale Hand", "resources": 38, "goal_tier": "dominance"})
    state.upsert_faction({"id": "F2", "name": "Ashers", "resources": 1, "goal_tier": "survival"})
    for _ in range(400):
        factions.tick()
    for fid in ("F1", "F2"):
        res = state.get_faction(fid)["resources"]
        assert factions.RES_MIN <= res <= factions.RES_MAX


# #1 — re-applying a condition refreshes duration, never stacks duplicates
def test_condition_add_dedupes(fresh_db):
    _hero()
    for rounds in ("3", "5", "2"):
        mechanics.apply_mechanics([Mechanic(tag="CONDITION_ADD", args=["Kaelrath", "Exhaustion", rounds],
                                            raw=f"CONDITION_ADD: Kaelrath, Exhaustion, {rounds}")])
    conds = state.get_pc("PC-h")["conditions"]
    assert conds == [{"name": "Exhaustion", "rounds": 2}]   # one entry, latest duration


# DM quest closure: QUEST_COMPLETE must actually close + fuzzy-match the title
def test_quest_complete_closes_quest(fresh_db):
    mechanics.apply_mechanics([Mechanic(tag="QUEST_ADD", args=["Slay the Frost Wyrm", "kill it"],
                                        raw="QUEST_ADD: Slay the Frost Wyrm, kill it")])
    # the model emits the natural tag with NO status arg — used to be a silent no-op
    mechanics.apply_mechanics([Mechanic(tag="QUEST_COMPLETE", args=["Slay the Frost Wyrm"],
                                        raw="QUEST_COMPLETE: Slay the Frost Wyrm")])
    q = [x for x in state.list_quests() if x["title"] == "Slay the Frost Wyrm"][0]
    assert q["status"] == "completed"


def test_quest_complete_fuzzy_title(fresh_db):
    mechanics.apply_mechanics([Mechanic(tag="QUEST_ADD", args=["The Obsidian Spine"], raw="QUEST_ADD: The Obsidian Spine")])
    # DM paraphrases the title -> unique-substring match still closes it
    mechanics.apply_mechanics([Mechanic(tag="QUEST_COMPLETE", args=["Obsidian Spine"], raw="QUEST_COMPLETE: Obsidian Spine")])
    assert [x for x in state.list_quests() if x["title"] == "The Obsidian Spine"][0]["status"] == "completed"


# ITEM_ADD with a first name ("Kaelrath" vs "Kaelrath Emberhide") must strip the PC, not bake it in
def test_item_add_first_name_strips_pc(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath Emberhide", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "inventory": []})
    mechanics.apply_mechanics([Mechanic(tag="ITEM_ADD", args=["Kaelrath", "A Shiny Sword", "1"],
                                        raw="ITEM_ADD: Kaelrath, A Shiny Sword, 1")])
    inv = state.get_pc("PC-1")["inventory"]
    assert inv == [{"item": "A Shiny Sword", "qty": 1}]   # not "Kaelrath, A Shiny Sword"


def test_item_add_no_pc_keeps_full_name(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kaelrath Emberhide", "is_player": 1, "hp": 10, "max_hp": 10,
                     "ac": 10, "inventory": []})
    # an item that merely contains a name must NOT be eaten as the PC
    mechanics.apply_mechanics([Mechanic(tag="ITEM_ADD", args=["Talmarr's locket", "1"],
                                        raw="ITEM_ADD: Talmarr's locket, 1")])
    assert state.get_pc("PC-1")["inventory"] == [{"item": "Talmarr's locket", "qty": 1}]
