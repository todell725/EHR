import json

from backend.api import ascension
from backend.memory import working


def test_default_state_has_four_domains(fresh_db):
    st = ascension.get_state()
    assert st["total"] == 4
    assert st["claimed"] == 0
    assert any(d["domain"] == "Dream" and d["status"] == "in_progress" for d in st["domains"])


def test_advance_domain(fresh_db):
    ascension.set_domain(ascension.DomainUpdate(domain="dream", status="claimed"))
    ascension.set_domain(ascension.DomainUpdate(domain="Memory", status="in_progress",
                                                crystal="The Sister Anchor"))
    st = ascension.get_state()
    assert st["claimed"] == 1
    mem = next(d for d in st["domains"] if d["domain"] == "Memory")
    assert mem["status"] == "in_progress" and mem["crystal"] == "The Sister Anchor"


def test_arc_note_injected_into_scene_block(fresh_db):
    fresh_db.execute(
        "INSERT INTO meta (key, value) VALUES ('arc_note', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ["RELIEVE the four anchors and offer his mortality."],
    )
    block = working.build_scene_block()
    assert "CAMPAIGN ARC" in block
    assert "RELIEVE the four anchors" in block


def test_no_arc_note_means_no_block(fresh_db):
    assert "CAMPAIGN ARC" not in working.build_scene_block()
