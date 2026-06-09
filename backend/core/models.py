"""Pydantic models: entity shapes for the API and the DM output contract.

These are *boundary* types (request/response, parsed-LLM-output). Persistence uses
plain dict rows via `backend.core.db`; we convert at the edges. Keeping the DB
layer ORM-free and the API layer typed is the deliberate split.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ArcPhase = Literal["origins", "kingdom"]
Era = Literal["present", "future_foreshadow"]


# ----------------------------------------------------------------- entity views
class WorldState(BaseModel):
    arc_phase: ArcPhase = "origins"
    domain_ruled: bool = False
    year: int = 1
    month: int = 1
    day: int = 1
    season: str = "The Sowing"
    time_of_day: str = "morning"
    weather: str = "clear"
    location_id: str | None = None
    global_events: list[Any] = Field(default_factory=list)
    turn_counter: int = 0


class PlayerCharacter(BaseModel):
    id: str
    name: str
    race: str | None = None
    class_: str | None = Field(default=None, alias="class")
    subclass: str | None = None
    level: int = 1
    xp: int = 0
    hp: int = 10
    max_hp: int = 10
    ac: int = 10
    abilities: dict[str, int] = Field(default_factory=dict)
    conditions: list[dict] = Field(default_factory=list)
    inventory: list[dict] = Field(default_factory=list)
    skills: dict[str, int] = Field(default_factory=dict)
    custom_dice: dict[str, Any] = Field(default_factory=dict)
    status: str = "alive"

    model_config = {"populate_by_name": True}


class NPC(BaseModel):
    id: str
    name: str
    race: str | None = None
    role: str | None = None
    faction_id: str | None = None
    location_id: str | None = None
    domains: list[str] = Field(default_factory=list)
    personality: list[str] = Field(default_factory=list)
    secret: str | None = None
    want: str | None = None
    need: str | None = None
    fear: str | None = None
    bio: str = ""
    motivation: str = ""
    disposition: dict[str, int] = Field(default_factory=dict)
    status: str = "alive"
    era: Era = "present"


# ------------------------------------------------------------ DM output contract
MechanicTag = Literal[
    "HP_CHANGE", "ENEMY_HP", "ROLL_REQUEST", "SAVE_REQUEST",
    "CONDITION_ADD", "CONDITION_REMOVE", "ITEM_ADD", "ITEM_REMOVE",
    "XP_GRANT", "NPC_DISPOSITION_CHANGE", "FACTION_REP_CHANGE",
    "QUEST_UPDATE", "QUEST_ADD", "WORLD_EVENT", "WORLD_HOOK",
    "NPC_SPAWN", "NPC_STATUS", "TIME_ADVANCE", "COMBAT_START", "COMBAT_END",
]


class Mechanic(BaseModel):
    """One parsed `[MECHANICS]` directive, e.g. `HP_CHANGE: Kael, -8`."""
    tag: str
    args: list[str] = Field(default_factory=list)
    raw: str = ""


class Suggestion(BaseModel):
    text: str
    requires_roll: bool = False
    roll_hint: str | None = None  # e.g. "STR Athletics"


class ParsedTurn(BaseModel):
    """The fully parsed four-section DM response."""
    narrative: str = ""
    mechanics: list[Mechanic] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    chronicle: str | None = None
    parse_ok: bool = True
    parse_notes: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- API models
class PlayAction(BaseModel):
    text: str = Field(..., min_length=1)
    pc_id: str | None = None  # which character acts (multi-PC ready)


class RollResult(BaseModel):
    expression: str
    label: str
    rolls: list[int]
    modifier: int
    total: int
    outcome: str | None = None  # SUCCESS | FAILURE | CRIT | FUMBLE when a DC is known
    dc: int | None = None
