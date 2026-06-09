"""Mount endpoints — tamed/ridden creatures bonded to a hero (the stable)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import state

router = APIRouter(prefix="/api/mounts", tags=["mounts"])


@router.get("")
def list_mounts() -> list[dict]:
    return state.list_mounts()


class NewMount(BaseModel):
    name: str
    kind: str = "horse"
    owner_pc_id: str | None = None
    traits: list[str] = []
    speed: int = 60
    max_hp: int = 15
    notes: str = ""


@router.post("")
def create_mount(body: NewMount) -> dict:
    owner = body.owner_pc_id
    if not owner:                       # default to the player's hero
        heroes = state.heroes()
        owner = heroes[0]["id"] if heroes else None
    mid = "MNT-" + uuid.uuid4().hex[:6]
    state.upsert_mount({
        "id": mid, "name": body.name, "kind": body.kind, "owner_pc_id": owner,
        "hp": body.max_hp, "max_hp": body.max_hp, "speed": body.speed,
        "traits": body.traits, "notes": body.notes, "status": "active", "active": 1, "bond": 1,
    })
    return state.get_mount(mid)


class UpdateMount(BaseModel):
    name: str | None = None
    hp: int | None = None
    max_hp: int | None = None
    bond: int | None = None
    speed: int | None = None
    status: str | None = None
    active: bool | None = None
    notes: str | None = None
    traits: list[str] | None = None


@router.post("/{mount_id}")
def update_mount(mount_id: str, body: UpdateMount) -> dict:
    if not state.get_mount(mount_id):
        raise HTTPException(404, "no such mount")
    upd: dict = {"id": mount_id}
    for f in ("name", "hp", "max_hp", "bond", "speed", "status", "notes", "traits"):
        v = getattr(body, f)
        if v is not None:
            upd[f] = v
    if body.active is not None:
        upd["active"] = 1 if body.active else 0
    state.upsert_mount(upd)
    return state.get_mount(mount_id)


@router.delete("/{mount_id}")
def delete_mount(mount_id: str) -> dict:
    if not state.get_mount(mount_id):
        raise HTTPException(404, "no such mount")
    state.upsert_mount({"id": mount_id, "status": "dead", "active": 0})  # soft-remove
    return {"ok": True}
