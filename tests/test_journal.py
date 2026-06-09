from backend.core import state
from backend.core.models import Mechanic
from backend.dm import mechanics


def test_journal_mechanic_writes_entry(fresh_db):
    res = mechanics.apply_mechanics([Mechanic(
        tag="JOURNAL", args=["wistful", "I told her the truth, and the world did not end"],
        raw="JOURNAL: wistful, I told her the truth, and the world did not end")])
    assert any("journal" in a for a in res["applied"])
    entries = state.list_journal()
    assert len(entries) == 1
    assert entries[0]["mood"] == "wistful"
    assert "the world did not end" in entries[0]["body"]


def test_journal_alias_and_comma_body(fresh_db):
    # an invented synonym maps to JOURNAL; commas in the body are preserved
    mechanics.apply_mechanics([Mechanic(
        tag="FEELS", args=["heavy", "I carry her burden", "and his", "and still I stand"],
        raw="FEELS: heavy, I carry her burden, and his, and still I stand")])
    body = state.list_journal()[0]["body"]
    assert body == "I carry her burden, and his, and still I stand"


def test_add_list_delete_journal(fresh_db):
    a = state.add_journal("First", "a quiet fear", mood="uneasy")
    state.add_journal("Second", "a warm bond", mood="tender")
    entries = state.list_journal()
    assert len(entries) == 2
    assert entries[0]["title"] == "Second"          # newest first
    assert entries[0]["mood"] == "tender"

    assert state.delete_journal(a) is True
    assert len(state.list_journal()) == 1
    assert state.delete_journal(99999) is False
