"""Layer 2 — semantic memory (RAG).

Embeddings come from a fixed local model (Ollama `nomic-embed-text`) and are stored
as raw float32 BLOBs in the `memory_chunks` table. Retrieval is brute-force cosine
in numpy: the corpus is well under 10k chunks, so a vector server (Chroma/Qdrant)
would be pure overhead. If the campaign ever outgrows this, swap *only* this module.

Hard rule: never change `EMBED_MODEL` once the store is populated — mixing embedding
models silently breaks similarity. `dims` is recorded per row as a tripwire.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from backend.core import db
from backend.core.config import settings
from backend.llm.client import get_llm

logger = logging.getLogger("emberheart.rag")


# ----------------------------------------------------------------- serialization
def to_blob(vec: list[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# ------------------------------------------------------------------- chunking
def chunk_text(text: str, *, max_words: int = 380, overlap: int = 40) -> list[str]:
    """Word-windowed chunking (~512 tokens / 50 overlap for prose).

    Use a smaller `max_words` (~96) for discrete facts like NPC stat lines.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()] if text.strip() else []
    chunks, start = [], 0
    step = max(1, max_words - overlap)
    while start < len(words):
        chunks.append(" ".join(words[start : start + max_words]))
        start += step
    return chunks


# --------------------------------------------------------------------- writing
async def store(
    text: str,
    *,
    kind: str,
    ref_id: str | None = None,
    source: str = "",
    era: str = "present",
    seed: bool = False,
) -> int | None:
    """Embed one chunk and persist it. Returns the row id (or None on failure)."""
    text = text.strip()
    if not text:
        return None
    try:
        vec = await get_llm().embed(text)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully if Ollama is down
        logger.warning("embed failed (%s); storing chunk without vector", exc)
        vec = None
    cur = db.execute(
        "INSERT INTO memory_chunks (kind, ref_id, source, text, embedding, dims, era, seed) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            kind, ref_id, source, text,
            to_blob(vec) if vec else None,
            len(vec) if vec else None,
            era, 1 if seed else 0,
        ],
    )
    return cur.lastrowid


async def store_chunks(
    text: str,
    *,
    kind: str,
    ref_id: str | None = None,
    source: str = "",
    era: str = "present",
    seed: bool = False,
    max_words: int = 380,
    overlap: int = 40,
) -> int:
    """Chunk a longer document, batch-embed, and persist. Returns count stored."""
    chunks = chunk_text(text, max_words=max_words, overlap=overlap)
    if not chunks:
        return 0
    try:
        vecs = await get_llm().embed_batch(chunks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch embed failed (%s); storing without vectors", exc)
        vecs = [None] * len(chunks)
    rows = [
        (kind, ref_id, source, c, to_blob(v) if v else None,
         len(v) if v else None, era, 1 if seed else 0)
        for c, v in zip(chunks, vecs)
    ]
    db.executemany(
        "INSERT INTO memory_chunks (kind, ref_id, source, text, embedding, dims, era, seed) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


async def remember(text: str, *, kind: str = "note", ref_id: str | None = None) -> int | None:
    """Convenience write-back used during play (chronicle beats, GM notes)."""
    return await store(text, kind=kind, ref_id=ref_id, source="play")


# ------------------------------------------------------------------- retrieval
async def retrieve(
    query: str,
    *,
    k: int | None = None,
    threshold: float | None = None,
    include_future: bool = False,
) -> list[dict]:
    """Top-k semantically relevant memories above a relevance threshold.

    Returns `[{id, kind, text, score, era, source}]`. Below-threshold matches are
    dropped (return nothing rather than inject noise — per spec).
    """
    k = k or settings.rag_top_k
    threshold = settings.rag_relevance_threshold if threshold is None else threshold

    try:
        q = np.asarray(await get_llm().embed(query), dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("query embed failed (%s); returning no memories", exc)
        return []

    era_filter = "" if include_future else "AND era = 'present'"
    rows = db.query(
        f"SELECT id, kind, text, embedding, era, source FROM memory_chunks "
        f"WHERE embedding IS NOT NULL {era_filter}"
    )
    if not rows:
        return []
    if len(rows) > 20000:  # brute-force cosine is O(N) — fine for now, plan an index past here
        logger.warning("RAG scanning %d chunks; consider a vector index or tighter era filter.", len(rows))

    def _rank() -> list[dict]:
        # cosine = normalized dot product
        mat = np.vstack([from_blob(r["embedding"]) for r in rows])
        qn = q / (np.linalg.norm(q) + 1e-9)
        mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        scores = mn @ qn

        # Scan more than k so we can drop near-duplicates and still fill k slots.
        order = np.argsort(scores)[::-1][: k * 4]
        out: list[dict] = []
        seen: list[set[str]] = []
        for i in order:
            score = float(scores[i])
            if score < threshold:
                break  # sorted desc — nothing better remains
            r = rows[i]
            # cheap near-duplicate guard: high token-overlap with an already-picked chunk
            toks = set(r["text"].lower().split())
            if any(toks and len(toks & s) / len(toks) > 0.8 for s in seen):
                continue
            seen.append(toks)
            out.append(
                {"id": r["id"], "kind": r["kind"], "text": r["text"],
                 "score": round(score, 4), "era": r["era"], "source": r["source"]}
            )
            if len(out) >= k:
                break
        return out

    # the vstack + matmul + rank is synchronous CPU work; run it off the event loop so a
    # big memory_chunks table can't stall the WebSocket stream / UI during retrieval.
    return await asyncio.to_thread(_rank)


def count() -> dict:
    total = db.query_one("SELECT COUNT(*) c FROM memory_chunks")["c"]
    embedded = db.query_one(
        "SELECT COUNT(*) c FROM memory_chunks WHERE embedding IS NOT NULL"
    )["c"]
    return {"total": total, "embedded": embedded}
