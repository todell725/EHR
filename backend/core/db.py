"""SQLite access layer.

Thin, dependency-free DAL over the stdlib `sqlite3`. We deliberately avoid an ORM
(lean-tooling preference): the schema is small, hand-written, and the LLM never
writes it directly — all mutations flow through typed helpers here, invoked by the
deterministic mechanics layer.

Conventions:
  * one connection per thread (sqlite3 connections aren't shareable across threads);
  * WAL mode + foreign keys on;
  * JSON columns are (de)serialised with the `jcol` / `dumps` helpers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from backend.core.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 8  # bump when adding a MIGRATIONS entry

# Forward-only migrations applied after the (idempotent) base schema. Each entry is
# (target_user_version, sql). Add new ones here; never edit shipped entries.
MIGRATIONS: list[tuple[int, str]] = [
    # v2: persistent "current scene" line so the DM stays grounded over long sessions.
    (2, "ALTER TABLE world_state ADD COLUMN scene TEXT NOT NULL DEFAULT '';"),
    # v3: NPC pronouns so the DM doesn't misgender characters.
    (3, "ALTER TABLE npcs ADD COLUMN pronouns TEXT NOT NULL DEFAULT '';"),
    # v4: known features/actions/spells per PC (the character sheet's progression).
    (4, "ALTER TABLE player_characters ADD COLUMN features TEXT NOT NULL DEFAULT '[]';"),
    # v5: private 1-on-1 out-of-campaign chats with party companions.
    (5, "CREATE TABLE IF NOT EXISTS companion_chats ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, character_id TEXT NOT NULL, "
        "role TEXT NOT NULL, content TEXT NOT NULL, "
        "ts REAL NOT NULL DEFAULT (unixepoch('subsec')));"),
    # v6: accumulated XP per idle skill (smithing/hunting/...) -> derives the skill level.
    (6, "ALTER TABLE player_characters ADD COLUMN skill_xp TEXT NOT NULL DEFAULT '{}';"),
    # v7: the journal — reflective "feels" entries (not quests): moods, fears, bonds.
    (7, "CREATE TABLE IF NOT EXISTS journal ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', "
        "body TEXT NOT NULL DEFAULT '', mood TEXT NOT NULL DEFAULT '', "
        "in_world_date TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT 'Kaelrath', "
        "ts REAL NOT NULL DEFAULT (unixepoch('subsec')));"),
    # v8: mounts — tamed/ridden creatures bonded to a hero.
    (8, "CREATE TABLE IF NOT EXISTS mounts ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'horse', "
        "owner_pc_id TEXT, hp INTEGER NOT NULL DEFAULT 15, max_hp INTEGER NOT NULL DEFAULT 15, "
        "speed INTEGER NOT NULL DEFAULT 60, bond INTEGER NOT NULL DEFAULT 1, "
        "traits TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active', "
        "active INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '');"),
]

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Return this thread's connection, opening it on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(
            settings.db_path_resolved,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create tables (idempotent) and seed the singleton world_state row."""
    conn = get_conn()
    conn.executescript(SCHEMA_PATH.read_text())

    # Apply forward-only migrations gated on user_version.
    current = conn.execute("PRAGMA user_version;").fetchone()[0]
    for version, sql in MIGRATIONS:
        if version > current:
            try:
                conn.executescript(sql)
            except sqlite3.OperationalError as exc:
                # tolerate a column that already exists (e.g. mixed dev DBs)
                if "duplicate column" not in str(exc).lower():
                    raise
            conn.execute(f"PRAGMA user_version = {version};")
            current = version
    if current < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")

    # Guarantee the singleton world_state exists.
    conn.execute(
        "INSERT OR IGNORE INTO world_state (id) VALUES (1);"
    )
    conn.commit()


# ----------------------------------------------------------------- json helpers
def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def jcol(row: sqlite3.Row | dict, key: str, default: Any = None) -> Any:
    """Decode a JSON text column, tolerating missing/empty values."""
    raw = row[key] if key in row.keys() else None  # type: ignore[union-attr]
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


# ------------------------------------------------------------- query utilities
def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return get_conn().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = get_conn()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    conn = get_conn()
    conn.executemany(sql, [tuple(p) for p in seq])
    conn.commit()


def upsert(table: str, data: dict[str, Any], pk: str = "id") -> None:
    """Insert a new row, or partial-update an existing one.

    Update-if-exists (rather than INSERT ... ON CONFLICT) so callers can pass just the
    columns they want to change: a bare `{"id": x, "hp": 3}` updates only `hp` without
    tripping NOT NULL on unspecified columns. New rows must supply all required columns.
    JSON-encodes list/dict values automatically.
    """
    clean = {
        k: (dumps(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()
    }
    exists = query_one(f"SELECT 1 FROM {table} WHERE {pk} = ?", [clean[pk]])
    if exists:
        cols = [c for c in clean if c != pk]
        if not cols:
            return
        sets = ", ".join(f"{c} = ?" for c in cols)
        execute(
            f"UPDATE {table} SET {sets} WHERE {pk} = ?",
            [clean[c] for c in cols] + [clean[pk]],
        )
    else:
        cols = ", ".join(clean)
        placeholders = ", ".join(["?"] * len(clean))
        execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(clean.values()),
        )


def row_to_dict(row: sqlite3.Row | None, json_cols: Iterable[str] = ()) -> dict | None:
    """Convert a Row to a dict, decoding the named JSON columns."""
    if row is None:
        return None
    d = dict(row)
    for c in json_cols:
        if c in d:
            d[c] = jcol(row, c, default=d[c])
    return d
