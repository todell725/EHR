"""The journal — where feels go. Reflective entries (moods, fears, bonds), not quests."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import state

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
def list_entries() -> list[dict]:
    return state.list_journal()


class NewEntry(BaseModel):
    title: str = ""
    body: str
    mood: str = ""
    in_world_date: str = ""
    author: str = "Kaelrath"


@router.post("")
def add_entry(body: NewEntry) -> dict:
    eid = state.add_journal(body.title, body.body, mood=body.mood,
                            in_world_date=body.in_world_date, author=body.author)
    return {"id": eid}


@router.delete("/{entry_id}")
def delete_entry(entry_id: int) -> dict:
    if not state.delete_journal(entry_id):
        raise HTTPException(404, "no such entry")
    return {"ok": True}
