"""Pytest setup — point the DB at a throwaway file before backend imports load config."""

import os
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest  # noqa: E402

from backend.core import db  # noqa: E402


@pytest.fixture()
def fresh_db():
    """A clean, initialised database for state/sim tests."""
    # wipe any prior thread connection + file
    conn = db.get_conn()
    conn.close()
    db._local.conn = None  # type: ignore[attr-defined]
    path = os.environ["DB_PATH"]
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass
    db.init_db()
    yield db
