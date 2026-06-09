"""Snapshot / undo safety-net tests."""

from backend.core import backups, state


def test_undo_restores_prior_state(fresh_db):
    state.update_world(day=1)
    backups.pre_turn_snapshot(1)
    state.update_world(day=5)
    assert state.get_world()["day"] == 5

    res = backups.undo()
    assert res is not None
    assert state.get_world()["day"] == 1


def test_undo_with_nothing_returns_none(fresh_db):
    # clear any snapshots a prior test left
    for p in backups._snap_dir().glob("*.db"):
        p.unlink()
    assert backups.undo() is None


def test_backup_creates_file(fresh_db):
    path = backups.backup("test-label")
    assert path.exists()
    assert "test-label" in path.name
