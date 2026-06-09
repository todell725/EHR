"""Campaign safety net — snapshots, undo, and exportable backups.

Two kinds of snapshot, both made with SQLite's online backup API (a consistent
page-level copy that works while the live connection stays open):

  * **pre-turn snapshots** (a small ring) power *undo last turn*;
  * **session/manual backups** are durable, labelled copies you can export.

Restore copies a snapshot *into* the live connection (`src.backup(live)`), so there's
no file-swap and no need to close the running server's connection.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from backend.core import db
from backend.core.config import settings

SNAP_KEEP = 15   # pre-turn ring depth (how many undos deep you can go)
BACKUP_KEEP = 20  # labelled backups retained


def _base() -> Path:
    return settings.db_path_resolved.parent


def _snap_dir() -> Path:
    d = _base() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_dir() -> Path:
    d = _base() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_to(path: Path) -> Path:
    dest = sqlite3.connect(path)
    try:
        db.get_conn().backup(dest)
    finally:
        dest.close()
    return path


def _restore_from(path: Path) -> None:
    src = sqlite3.connect(path)
    try:
        src.backup(db.get_conn())
    finally:
        src.close()
    db.get_conn().commit()


def _prune(directory: Path, keep: int) -> None:
    files = sorted(directory.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


# ------------------------------------------------------------------ pre-turn ring
def pre_turn_snapshot(turn: int) -> Path:
    """Snapshot state *before* a turn mutates it. Called by the orchestrator."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = _snap_dir() / f"turn-{turn:06d}-{ts}.db"
    _snapshot_to(path)
    _prune(_snap_dir(), SNAP_KEEP)
    return path


def latest_snapshot() -> Path | None:
    snaps = sorted(_snap_dir().glob("turn-*.db"), key=lambda p: p.stat().st_mtime)
    return snaps[-1] if snaps else None


def undo() -> dict | None:
    """Roll back to the most recent pre-turn snapshot and consume it."""
    snap = latest_snapshot()
    if snap is None:
        return None
    _restore_from(snap)
    turn = snap.name.split("-")[1]
    snap.unlink(missing_ok=True)  # so a second undo steps further back
    return {"restored_before_turn": turn, "remaining_undos": len(list(_snap_dir().glob("turn-*.db")))}


# -------------------------------------------------------------- labelled backups
def backup(label: str = "manual") -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = _backup_dir() / f"{safe}-{ts}.db"
    _snapshot_to(path)
    _prune(_backup_dir(), BACKUP_KEEP)
    return path


def export_copy() -> Path:
    """A fresh standalone snapshot suitable for download."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = _backup_dir() / f"export-{ts}.db"
    return _snapshot_to(path)


def list_all() -> dict:
    def meta(p: Path) -> dict:
        st = p.stat()
        return {"name": p.name, "size": st.st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}

    return {
        "snapshots": [meta(p) for p in sorted(_snap_dir().glob("turn-*.db"),
                                              key=lambda p: p.stat().st_mtime, reverse=True)],
        "backups": [meta(p) for p in sorted(_backup_dir().glob("*.db"),
                                            key=lambda p: p.stat().st_mtime, reverse=True)],
    }
