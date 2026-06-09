#!/usr/bin/env python
"""Re-embed the entire memory corpus with a new EMBED_MODEL.

This is the migration path off `nomic-embed-text` — the one previously-permanent
decision. Pick a better embedding model, run this once, then set EMBED_MODEL in .env
to match and redeploy. Every `memory_chunks` row is re-embedded and its `dims` updated,
so the store stays internally consistent (no mixed-model cosine).

Backs the DB up first; processes in batches; safe to re-run.

Usage (from the repo root):
    .venv/bin/python scripts/reembed.py <new-model>
    REEMBED_MODEL=<new-model> .venv/bin/python scripts/reembed.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time

import numpy as np

from backend.core import db
from backend.core.config import settings
from backend.llm.client import get_llm

BATCH = 64


async def main() -> int:
    target = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("REEMBED_MODEL") or settings.embed_model
    db.init_db()
    rows = db.query("SELECT id, text FROM memory_chunks WHERE text IS NOT NULL AND text != ''")
    if not rows:
        print("no chunks to re-embed — nothing to do.")
        return 0

    src = settings.db_path_resolved
    bak = src.with_suffix(src.suffix + f".reembed-bak-{int(time.time())}")
    shutil.copy2(src, bak)
    print(f"backed up DB -> {bak}")
    print(f"re-embedding {len(rows)} chunks with '{target}' (current EMBED_MODEL='{settings.embed_model}')")

    settings.embed_model = target          # client.embed_batch reads this per call
    done = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        try:
            vecs = await get_llm().embed_batch([r["text"] for r in batch])
        except Exception as exc:  # noqa: BLE001
            print(f"  batch at {i} failed: {exc} — aborting (DB backup is at {bak})")
            return 1
        for r, v in zip(batch, vecs):
            db.execute("UPDATE memory_chunks SET embedding = ?, dims = ? WHERE id = ?",
                       [np.asarray(v, dtype=np.float32).tobytes(), len(v), r["id"]])
        done += len(batch)
        print(f"  {done}/{len(rows)}")

    dims = {r["dims"] for r in db.query("SELECT DISTINCT dims FROM memory_chunks WHERE embedding IS NOT NULL")}
    print(f"done. all rows now {dims} dims.")
    print(f"NEXT: set EMBED_MODEL={target} in .env and redeploy so new embeds match.")
    await get_llm().close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
