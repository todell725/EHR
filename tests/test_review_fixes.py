"""Locks the A–D review fixes."""
from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.dm.orchestrator import _looks_truncated
from backend.sim import factions


# Truncation guard: a beat cut mid-word must be flagged for regeneration
def test_truncation_guard_flags_midword_cut():
    # the real failure: stream ended at "...listening from th"
    assert _looks_truncated(
        "The column is strung out, the anchor singing, but the void is listening from th") is True
    # mid-clause comma is also a cut
    assert _looks_truncated("Renn steps forward and the rangers close up around the cart,") is True


def test_truncation_guard_accepts_finished_beats():
    assert _looks_truncated("The pines rise ahead, dark against the glacier's shoulder.") is False
    assert _looks_truncated('"Something matched the harmonic," she says, voice tight.') is False
    assert _looks_truncated("The shadows between the trees have gone too still—") is False  # em-dash cliffhanger
    assert _looks_truncated("*The violet shimmer threads through the lower branches.*") is False
    # too-short is the garbled-guard's job, not the truncation guard's
    assert _looks_truncated("###") is False
    assert _looks_truncated("") is False


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


# Council appointments must land in structured state so the roster survives any model
def test_council_appoint_seats_npc_with_portfolio(fresh_db):
    state.upsert_npc({"id": "NPC-c", "name": "Corin", "role": "Foreman"})
    mechanics.apply_mechanics([Mechanic(tag="COUNCIL_APPOINT",
                                        args=["Corin", "the hearth-channels", "industry"],
                                        raw="COUNCIL_APPOINT: Corin, the hearth-channels, industry")])
    seated = state.list_council()
    assert [n["name"] for n in seated] == ["Corin"]
    assert seated[0]["council"] == "the hearth-channels, industry"


def test_council_appoint_aliases_route(fresh_db):
    state.upsert_npc({"id": "NPC-a", "name": "Aldra", "role": "Scout"})
    # the model's natural phrasing ("APPOINT") must canonicalize to COUNCIL_APPOINT
    mechanics.apply_mechanics([Mechanic(tag="APPOINT", args=["Aldra", "the borderlands"],
                                        raw="APPOINT: Aldra, the borderlands")])
    assert [n["name"] for n in state.list_council()] == ["Aldra"]


# A short/first name must resolve to the full-named NPC, never spawn a duplicate stub
def test_find_npc_first_name_resolves_to_full(fresh_db):
    state.upsert_npc({"id": "NPC-v", "name": "Vaelis Thorne", "disposition": {"PC-01": 182}})
    found = state.find_npc_by_name("Vaelis")          # the short name a beat would use
    assert found and found["id"] == "NPC-v"
    assert found["disposition"]["PC-01"] == 182


def test_ensure_npc_does_not_stub_a_known_companion(fresh_db):
    state.upsert_pc({"id": "PC-01", "name": "Kaelrath Emberhide", "is_player": 1})
    state.upsert_npc({"id": "NPC-v", "name": "Vaelis Thorne", "disposition": {"PC-01": 182}})
    # a disposition change addressed to "Vaelis" must land on the real record, not a stub
    mechanics.apply_mechanics([Mechanic(tag="NPC_DISPOSITION_CHANGE", args=["Vaelis", "+5"],
                                        raw="NPC_DISPOSITION_CHANGE: Vaelis, +5")],
                              acting_pc_id="PC-01")
    vaelises = [n for n in state.all_npcs() if n["name"].lower().startswith("vaelis")]
    assert len(vaelises) == 1                          # no stub spawned
    assert vaelises[0]["disposition"]["PC-01"] == 187  # 182 + 5, on the real record


def test_find_npc_ambiguous_returns_none(fresh_db):
    # two characters sharing a first name -> don't guess
    state.upsert_npc({"id": "NPC-a", "name": "Vaelis Thorne"})
    state.upsert_npc({"id": "NPC-b", "name": "Vaelis Dunmar"})
    assert state.find_npc_by_name("Vaelis") is None


def test_find_npc_resolves_by_id(fresh_db):
    # even when the first name is ambiguous, the injected [id=...] resolves exactly
    state.upsert_npc({"id": "NPC-vaelis", "name": "Vaelis Thorne"})
    state.upsert_npc({"id": "NPC-other", "name": "Vaelis Dunmar"})
    assert state.find_npc("NPC-vaelis")["name"] == "Vaelis Thorne"
    assert state.find_npc("npc-vaelis")["name"] == "Vaelis Thorne"  # case-insensitive


def test_disposition_on_unknown_name_spawns_no_stub(fresh_db):
    state.upsert_pc({"id": "PC-01", "name": "Kaelrath Emberhide", "is_player": 1})
    before = len(state.all_npcs())
    res = mechanics.apply_mechanics([Mechanic(tag="NPC_DISPOSITION_CHANGE", args=["Nobody", "+40"],
                                              raw="NPC_DISPOSITION_CHANGE: Nobody, +40")],
                                    acting_pc_id="PC-01")
    assert len(state.all_npcs()) == before          # the phantom is never minted
    assert any("no known NPC" in n for n in res["notes"])


def test_council_dismiss_clears_seat(fresh_db):
    state.upsert_npc({"id": "NPC-b", "name": "Bheric", "role": "Forgemaster"})
    mechanics.apply_mechanics([Mechanic(tag="COUNCIL_APPOINT", args=["Bheric", "the forge"],
                                        raw="COUNCIL_APPOINT: Bheric, the forge")])
    assert state.list_council()
    mechanics.apply_mechanics([Mechanic(tag="COUNCIL_DISMISS", args=["Bheric"],
                                        raw="COUNCIL_DISMISS: Bheric")])
    assert state.list_council() == []
