"""Memory endpoints — inspect and probe the semantic store."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.memory import rag

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/stats")
def stats() -> dict:
    return rag.count()


class Search(BaseModel):
    query: str
    k: int | None = None
    include_future: bool = False


@router.post("/search")
async def search(body: Search) -> dict:
    results = await rag.retrieve(
        body.query, k=body.k, include_future=body.include_future
    )
    return {"results": results}


class Note(BaseModel):
    text: str
    kind: str = "note"


@router.post("/note")
async def note(body: Note) -> dict:
    rid = await rag.remember(body.text, kind=body.kind)
    return {"id": rid}
