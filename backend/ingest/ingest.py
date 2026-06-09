"""Corpus ingestion — seed the semantic memory from the existing EmberHeart material.

IMPORTANT framing (per the canon decision): this is a **fresh reboot**. The corpus is
ingested as *embedded seed lore the DM may draw on*, NOT as authoritative starting
state. We do not populate live PCs / NPCs / factions from the god-king save. Clearly
Golden-Age / post-scarcity / intergalactic content is tagged `era='future_foreshadow'`
so it stays out of the dark "origins" present and only surfaces as deep foreshadowing.

Idempotent: re-running first deletes prior seed rows (`seed = 1`) so counts don't drift.

Run:  python -m backend.ingest.ingest          (uses configured corpus paths)
      python -m backend.ingest.ingest --stats   (just print memory counts)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from backend.core import db
from backend.core.config import settings
from backend.memory import rag

logger = logging.getLogger("emberheart.ingest")

# Fallbacks if the env vars aren't set (the known workspace locations).
DEFAULT_CLAUDES = Path("/Users/todd/Projects/Dnd/Claudes-EmberHeart")
DEFAULT_ORIGINS = Path("/Users/todd/Projects/emberheart-origins")

# Keywords that mark a chunk as the far-future Golden Age, not the origins present.
_FUTURE_MARKERS = (
    "golden age", "post-scarcity", "post scarcity", "intergalactic", "eleventh age",
    "god-ascendant", "god ascendant", "ascended", "sacred gardner", "dual-galaxy",
    "world-spark", "steward", "divine monarchy", "infinite", "second moon",
    "celestial guard", "level 20", "522225", "transcendent", "galaxies",
)


def classify_era(text: str) -> str:
    low = text.lower()
    return "future_foreshadow" if any(m in low for m in _FUTURE_MARKERS) else "present"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read %s: %s", path, exc)
        return None


def _flatten(obj, keys: list[str]) -> str:
    """Pull a few human-readable fields out of a record into one text blob."""
    parts = []
    for k in keys:
        v = obj.get(k)
        if v:
            parts.append(f"{k}: {v}" if not isinstance(v, (list, dict)) else f"{k}: {json.dumps(v)}")
    return "\n".join(parts)


async def _ingest_npc_state(claudes: Path) -> int:
    path = claudes / "docs" / "NPC_STATE_FULL.json"
    data = _read_json(path)
    # File is {"version": ..., "npcs": [...]} — tolerate both that and a bare list.
    npcs = data.get("npcs") if isinstance(data, dict) else data
    if not isinstance(npcs, list):
        return 0
    n = 0
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        text = _flatten(npc, ["name", "race", "role", "description", "bio",
                              "motivation", "secret"])
        if not text:
            continue
        await rag.store(
            text, kind="npc", ref_id=str(npc.get("id")),
            source=str(path), era=classify_era(text), seed=True,
        )
        n += 1
    return n


async def _ingest_npc_profiles(claudes: Path) -> int:
    root = claudes / "characters" / "npcs"
    if not root.exists():
        return 0
    n = 0
    for prof in sorted(root.glob("*/profile.json")):
        npc = _read_json(prof)
        if not isinstance(npc, dict):
            continue
        text = _flatten(npc, ["name", "race", "role", "description", "bio",
                              "motivation", "secret"])
        if not text:
            continue
        await rag.store(
            text, kind="npc", ref_id=str(npc.get("id")),
            source=str(prof), era=classify_era(text), seed=True,
        )
        n += 1
    return n


async def _ingest_quests(claudes: Path) -> int:
    path = claudes / "docs" / "SIDE_QUESTS_DB.json"
    data = _read_json(path)
    quests = data if isinstance(data, list) else (data or {}).get("quests", [])
    if not isinstance(quests, list):
        return 0
    n = 0
    for q in quests:
        if not isinstance(q, dict):
            continue
        # short form only — title/desc/location/conclusion (skip turn-by-turn bulk)
        text = _flatten(q, ["title", "difficulty", "location", "district",
                            "description", "key_npcs", "conclusion"])
        if not text:
            continue
        await rag.store(
            text, kind="quest", ref_id=str(q.get("id")),
            source=str(path), era=classify_era(text), seed=True,
        )
        n += 1
    return n


async def _ingest_markdown(path: Path, kind: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text(errors="ignore")
    # chunk per-document; classify each chunk independently
    chunks = rag.chunk_text(text, max_words=380, overlap=40)
    n = 0
    for c in chunks:
        await rag.store(c, kind=kind, source=str(path), era=classify_era(c), seed=True)
        n += 1
    return n


async def _ingest_settlement(path: Path, label: str) -> int:
    data = _read_json(path)
    if not data:
        return 0
    text = f"{label} settlement snapshot (far-future reference):\n" + json.dumps(data)[:4000]
    # settlement snapshots are Golden-Age by nature -> foreshadow
    await rag.store(text, kind="lore", source=str(path),
                    era="future_foreshadow", seed=True)
    return 1


async def ingest_all() -> dict:
    db.init_db()

    claudes = settings.corpus_claudes_emberheart or DEFAULT_CLAUDES
    origins = settings.corpus_origins or DEFAULT_ORIGINS

    # idempotency: drop prior seed rows
    db.execute("DELETE FROM memory_chunks WHERE seed = 1")

    results: dict[str, int] = {}
    results["npc_state"] = await _ingest_npc_state(claudes)
    results["npc_profiles"] = await _ingest_npc_profiles(claudes)
    results["quests"] = await _ingest_quests(claudes)
    results["campaign_journal"] = await _ingest_markdown(
        claudes / "docs" / "CAMPAIGN_JOURNAL.md", kind="lore"
    )
    results["relationships"] = await _ingest_markdown(
        claudes / "docs" / "PARTY_RELATIONSHIPS.json", kind="npc"
    )
    results["orientations"] = await _ingest_markdown(
        claudes / "docs" / "NPC_ORIENTATIONS.json", kind="npc"
    )
    # session logs (several possible locations, incl. one dir up from the campaign)
    sess = 0
    log_dirs = [
        claudes / "session_logs",
        claudes / ".context" / "memories" / "session_logs",
        claudes.parent / "session_logs",
    ]
    for d in log_dirs:
        if d.exists():
            for f in sorted(d.glob("*.md")):
                sess += await _ingest_markdown(f, kind="session")
    results["session_logs"] = sess
    results["settlement_claudes"] = await _ingest_settlement(
        claudes / "docs" / "SETTLEMENT_STATE.json", "Claudes-EmberHeart"
    )
    results["settlement_origins"] = await _ingest_settlement(
        origins / "state" / "SETTLEMENT_STATE.json", "Origins"
    )

    results["_counts"] = rag.count()
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if "--stats" in sys.argv:
        db.init_db()
        print(json.dumps(rag.count(), indent=2))
        return
    summary = asyncio.run(ingest_all())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
