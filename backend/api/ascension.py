"""Ascension tracker — the hero's climb from god-touched to God-Ascendant.

Campaign-level state (one ascending hero): the EmberHeart at the center, four domain
anchors around it. Status per domain: unknown -> in_progress -> claimed. Stored in `meta`.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import db

router = APIRouter(prefix="/api/ascension", tags=["ascension"])

_DEFAULT = {
    "anchor": {"name": "The EmberHeart", "status": "bonded"},
    "domains": [
        {"domain": "Dream", "crystal": "The Ley-Anchor", "status": "in_progress"},
        {"domain": "Fire", "crystal": None, "status": "unknown"},
        {"domain": "Memory", "crystal": None, "status": "unknown"},
        {"domain": "Sacrifice", "crystal": None, "status": "unknown"},
    ],
    "rebirth": "Offer his mortality upon the EmberHeart — reborn the God-Ascendant Flamekeeper.",
}


def _get() -> dict:
    row = db.query_one("SELECT value FROM meta WHERE key = 'ascension'")
    return json.loads(row["value"]) if row else _DEFAULT


def _save(state: dict) -> None:
    db.execute("INSERT INTO meta (key, value) VALUES ('ascension', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", [json.dumps(state)])


@router.get("")
def get_state() -> dict:
    state = _get()
    claimed = sum(1 for d in state["domains"] if d["status"] == "claimed")
    return {**state, "claimed": claimed, "total": len(state["domains"])}


class DomainUpdate(BaseModel):
    domain: str
    status: str | None = None       # unknown | in_progress | claimed
    crystal: str | None = None


@router.post("/domain")
def set_domain(body: DomainUpdate) -> dict:
    state = _get()
    for d in state["domains"]:
        if d["domain"].lower() == body.domain.lower():
            if body.status:
                d["status"] = body.status
            if body.crystal is not None:
                d["crystal"] = body.crystal
            break
    _save(state)
    return get_state()
