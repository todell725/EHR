from backend.dm.parser import parse, parse_json

SAMPLE = """[NARRATIVE]
You step into the gloom. Aldric watches you, wary.

[MECHANICS]
HP_CHANGE: Kael, -3
XP_GRANT: 50
NPC_DISPOSITION_CHANGE: Aldric, -5

[SUGGESTIONS]
1. Back away slowly (requires roll: NO)
2. Draw your blade (requires roll: YES - STR Attack)
3. Try to reason with him (requires roll: YES - CHA Persuasion)

[CHRONICLE]
Kael entered the crypt and angered Aldric.
"""


def test_full_parse():
    p = parse(SAMPLE)
    assert p.parse_ok
    assert p.narrative.startswith("You step into the gloom")
    assert len(p.mechanics) == 3
    assert p.mechanics[0].tag == "HP_CHANGE"
    assert p.mechanics[0].args == ["Kael", "-3"]
    assert len(p.suggestions) == 3
    assert p.suggestions[0].requires_roll is False
    assert p.suggestions[1].requires_roll is True
    assert p.chronicle.startswith("Kael entered")


def test_markdown_headers_and_none():
    text = "**[NARRATIVE]**\nA quiet road.\n[MECHANICS]\nnone\n[SUGGESTIONS]\n1. Walk on (requires roll: NO)\n[CHRONICLE]\nnone"
    p = parse(text)
    assert p.parse_ok
    assert p.mechanics == []
    assert p.chronicle is None


def test_missing_narrative_flags_parse_fail():
    p = parse("[MECHANICS]\nnone")
    assert p.parse_ok is False
    assert any("NARRATIVE" in n for n in p.parse_notes)


def test_parse_json_objects_and_strings():
    text = """Sure, here you go: {
      "narrative": "You crest the ridge.",
      "mechanics": ["XP_GRANT: 25", {"tag": "HP_CHANGE", "args": ["Kael", -2]}],
      "suggestions": [{"text": "Descend", "requires_roll": true, "roll_hint": "DEX"}],
      "chronicle": "Kael crested the ridge."
    } hope that helps"""
    p = parse_json(text)
    assert p.parse_ok
    assert p.narrative == "You crest the ridge."
    tags = {m.tag for m in p.mechanics}
    assert {"XP_GRANT", "HP_CHANGE"} <= tags
    assert p.suggestions[0].requires_roll is True
    assert p.chronicle.startswith("Kael crested")


def test_parse_json_bad_input():
    assert parse_json("not json at all").parse_ok is False
