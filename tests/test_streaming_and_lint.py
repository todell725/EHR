from backend.core.models import Mechanic
from backend.dm import mechanics
from backend.dm.parser import streaming_narrative


def test_streaming_hides_forming_header():
    text, closed = streaming_narrative("[NAR")
    assert text == "" and closed is False


def test_streaming_strips_header_and_holds_tail():
    text, closed = streaming_narrative("[NARRATIVE]\nYou enter the long cold hall now.")
    assert closed is False
    assert text.startswith("You enter")
    assert "[" not in text  # header stripped


def test_streaming_closes_at_next_header():
    full = "[NARRATIVE]\nYou enter the hall.\n[MECHANICS]\nnone"
    text, closed = streaming_narrative(full)
    assert closed is True
    assert text == "You enter the hall."
    assert "MECHANICS" not in text


def test_unknown_tag_is_noted_not_rejected():
    res = mechanics.apply_mechanics([Mechanic(tag="DO_MAGIC", args=["x"], raw="DO_MAGIC: x")])
    assert res["applied"] == []
    assert res["rejected"] == []                      # no longer a hard rejection
    assert any("DO_MAGIC" in n for n in res["notes"])  # captured as a soft note


def test_linter_rejects_nonnumeric(fresh_db):
    from backend.core import state
    state.upsert_pc({"id": "PC-1", "name": "Kael", "hp": 10, "max_hp": 10, "ac": 10})
    res = mechanics.apply_mechanics(
        [Mechanic(tag="HP_CHANGE", args=["Kael", "lots"], raw="HP_CHANGE: Kael, lots")]
    )
    assert any("expected a number" in r for r in res["rejected"])


def test_valid_mechanic_applies(fresh_db):
    from backend.core import state
    state.upsert_pc({"id": "PC-1", "name": "Kael", "hp": 10, "max_hp": 10, "ac": 10})
    res = mechanics.apply_mechanics(
        [Mechanic(tag="HP_CHANGE", args=["Kael", "-3"], raw="HP_CHANGE: Kael, -3")]
    )
    assert res["rejected"] == []
    assert state.get_pc("PC-1")["hp"] == 7


def test_annotated_number_is_accepted(fresh_db):
    """The reported bug: '+5 (Trust/Urgency)' must apply, not get rejected."""
    from backend.core import state
    state.upsert_npc({"id": "EH-1", "name": "Talmarr", "disposition": {}})
    state.upsert_pc({"id": "PC-1", "name": "Kael", "hp": 10, "max_hp": 10, "ac": 10})
    res = mechanics.apply_mechanics(
        [Mechanic(tag="NPC_DISPOSITION_CHANGE", args=["Talmarr", "+5 (Trust/Urgency)"],
                  raw="NPC_DISPOSITION_CHANGE: Talmarr, +5 (Trust/Urgency)")],
        acting_pc_id="PC-1",
    )
    assert res["rejected"] == []
    assert state.get_npc("EH-1")["disposition"]["PC-1"] == 5


def test_coerce_int_extracts_leading_number():
    assert mechanics._coerce_int("+5 (Trust/Urgency)") == 5
    assert mechanics._coerce_int("8 damage") == 8
    assert mechanics._coerce_int("none", None) is None


def test_item_add_with_commas_in_description(fresh_db):
    from backend.core import state
    state.upsert_pc({"id": "PC-1", "name": "Ash", "hp": 10, "max_hp": 10, "ac": 10})
    res = mechanics.apply_mechanics(
        [Mechanic(tag="ITEM_ADD", args=["Ash", "a curious", "carved bone fragment", "1"],
                  raw="ITEM_ADD: Ash, a curious, carved bone fragment, 1")]
    )
    inv = state.get_pc("PC-1")["inventory"]
    assert inv == [{"item": "a curious, carved bone fragment", "qty": 1}]


def test_item_add_rejects_bare_number(fresh_db):
    from backend.core import state
    state.upsert_pc({"id": "PC-1", "name": "Ash", "hp": 10, "max_hp": 10, "ac": 10})
    mechanics.apply_mechanics([Mechanic(tag="ITEM_ADD", args=["Ash", "5"], raw="ITEM_ADD: Ash, 5")])
    assert state.get_pc("PC-1")["inventory"] == []  # junk number not added


def test_disposition_auto_registers_npc(fresh_db):
    from backend.core import state
    state.upsert_pc({"id": "PC-1", "name": "Ash", "hp": 10, "max_hp": 10, "ac": 10})
    assert state.find_npc_by_name("Talmarr") is None
    res = mechanics.apply_mechanics(
        [Mechanic(tag="NPC_DISPOSITION_CHANGE", args=["Talmarr", "+5 (trust)"],
                  raw="NPC_DISPOSITION_CHANGE: Talmarr, +5 (trust)")],
        acting_pc_id="PC-1",
    )
    npc = state.find_npc_by_name("Talmarr")
    assert npc is not None                       # auto-registered
    assert npc["disposition"]["PC-1"] == 5       # and the change applied
    assert npc["id"] in res["spawned"]           # queued for dossier fill


def test_scene_set_updates_world(fresh_db):
    from backend.core import state
    res = mechanics.apply_mechanics(
        [Mechanic(tag="SCENE_SET", args=["In the frozen ravine, hunting the wolf"],
                  raw="SCENE_SET: ...")]
    )
    assert res["rejected"] == []
    assert "ravine" in state.get_world()["scene"]
