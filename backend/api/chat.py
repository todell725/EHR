"""Private companion-chat endpoints (1-on-1, out of campaign)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core import state
from backend.dm import companion_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/partners")
def partners() -> dict:
    """Who you can talk to privately — your party companions."""
    return {"partners": [{"id": c["id"], "name": c["name"],
                          "race": c.get("race"), "class": c.get("class")}
                         for c in state.companions()]}


@router.get("/{character_id}")
def get_history(character_id: str) -> dict:
    if not state.get_pc(character_id):
        raise HTTPException(404, "companion not found")
    return {
        "history": companion_chat.history(character_id),
        "disposition": companion_chat.current_disposition(character_id),
    }


class Msg(BaseModel):
    text: str = Field(..., min_length=1)


@router.post("/{character_id}")
async def send(character_id: str, body: Msg) -> dict:
    result = await companion_chat.send(character_id, body.text)
    if result is None:
        raise HTTPException(404, "companion not found")
    return result  # {reply, delta, disposition}


@router.delete("/{character_id}")
def clear(character_id: str) -> dict:
    companion_chat.clear(character_id)
    return {"ok": True}
