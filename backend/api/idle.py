"""Idle-skilling endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.sim import idle

router = APIRouter(prefix="/api/idle", tags=["idle"])


@router.get("")
def get_state() -> dict:
    return idle.get_state()


class StartActivity(BaseModel):
    activity: str


@router.post("/start")
def start(body: StartActivity) -> dict:
    return idle.set_active(body.activity)


@router.post("/stop")
def stop() -> dict:
    return idle.set_active(None)


class Deposit(BaseModel):
    material: str
    qty: int


@router.post("/deposit")
def deposit(body: Deposit) -> dict:
    """Move gathered stores onto the hero's character sheet as a usable inventory item."""
    return idle.deposit_to_inventory(body.material, body.qty)
