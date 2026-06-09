from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics


def test_promote_npc_to_companion(fresh_db):
    state.upsert_npc({"id": "EH-9", "name": "Talmarr", "role": "Camp ally / scout",
                      "race": "Human", "pronouns": "she/her", "bio": "A wary scout."})
    pc = state.promote_npc_to_party("EH-9")
    assert pc is not None
    assert pc["is_player"] == 0           # DM-controlled
    assert pc["class"] == "Ranger"        # inferred from 'scout'
    assert pc["name"] == "Talmarr"
    assert state.get_npc("EH-9")["status"] == "party"   # left the active NPC roster
    assert any(p["id"] == pc["id"] for p in state.companions())
    assert pc["id"] not in [h["id"] for h in state.heroes()]


def test_party_join_mechanic(fresh_db):
    state.upsert_npc({"id": "EH-2", "name": "Borin", "role": "guard", "race": "Dwarf"})
    res = mechanics.apply_mechanics([Mechanic(tag="PARTY_JOIN", args=["Borin"],
                                              raw="PARTY_JOIN: Borin")])
    assert res["rejected"] == []
    assert any("Borin" in a for a in res["applied"])
    assert state.companions() and state.companions()[0]["name"] == "Borin"


def test_alias_routes_synonym_to_real_tag(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kael", "hp": 10, "max_hp": 10, "ac": 10,
                     "inventory": []})
    # 'LOOT' is not a real tag, but should alias to ITEM_ADD
    res = mechanics.apply_mechanics([Mechanic(tag="LOOT", args=["Kael", "rusty key"],
                                             raw="LOOT: Kael, rusty key")])
    assert res["rejected"] == [] and res["notes"] == []
    assert state.get_pc("PC-1")["inventory"][0]["item"] == "rusty key"


def test_damage_alias_applies_negative(fresh_db):
    state.upsert_pc({"id": "PC-1", "name": "Kael", "hp": 10, "max_hp": 10, "ac": 10})
    mechanics.apply_mechanics([Mechanic(tag="DAMAGE", args=["Kael", "4"], raw="DAMAGE: Kael, 4")])
    assert state.get_pc("PC-1")["hp"] == 6   # 'DAMAGE 4' -> HP_CHANGE -4, not +4


def test_unknown_tag_is_noted_not_rejected():
    res = mechanics.apply_mechanics([Mechanic(tag="WEATHER_VIBES", args=["ominous"],
                                             raw="WEATHER_VIBES: ominous")])
    assert res["rejected"] == []                          # not an error anymore
    assert any("WEATHER_VIBES" in n for n in res["notes"])  # captured + displayable
