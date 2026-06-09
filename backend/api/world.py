"""World & kingdom endpoints — the living-world dashboard + GM controls."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import db, state
from backend.sim import calendar, economy, factions, kingdom

router = APIRouter(prefix="/api/world", tags=["world"])


@router.get("")
def get_world() -> dict:
    world = state.get_world()
    return {
        "world": world,
        "factions": state.list_factions(),
        "quests": state.list_quests(),
        "hooks": state.open_hooks(),
        "domain": kingdom.get_domain(),
        "economy_enabled": economy.is_enabled(),
        "chronicle": state.recent_chronicle(limit=12),
        "kingdom_summary": kingdom.get_summary(),
    }


class Advance(BaseModel):
    amount: int = 1
    unit: str = "hours"


@router.post("/advance")
def advance(body: Advance) -> dict:
    fired = calendar.advance(body.amount, body.unit)
    return {"world": state.get_world(), "fired_events": fired}


@router.post("/faction-tick")
def faction_tick() -> dict:
    return {"moves": factions.tick(), "factions": state.list_factions()}


class FoundDomain(BaseModel):
    name: str
    enable_economy: bool = True


@router.post("/found-domain")
def found_domain(body: FoundDomain) -> dict:
    domain = kingdom.found_domain(body.name, enable_economy=body.enable_economy)
    return {"domain": domain, "world": state.get_world()}


class Invest(BaseModel):
    material: str
    qty: int


@router.post("/invest")
def invest(body: Invest) -> dict:
    """Pour gathered idle stores into the realm's stockpiles."""
    return kingdom.invest_material(body.material, body.qty)


@router.post("/seasonal-event")
def seasonal_event() -> dict:
    event = kingdom.seasonal_event()
    return {"event": event, "domain": kingdom.get_domain()}


@router.post("/economy-tick")
def economy_tick() -> dict:
    return {"delta": economy.tick(), "domain": kingdom.get_domain()}


class Toggle(BaseModel):
    on: bool


@router.post("/economy-toggle")
def economy_toggle(body: Toggle) -> dict:
    economy.set_enabled(body.on)
    return {"economy_enabled": economy.is_enabled()}


class LaborBody(BaseModel):
    labor: dict


@router.post("/labor")
def set_labor(body: LaborBody) -> dict:
    return kingdom.set_labor(body.labor)


@router.post("/labor-auto")
def auto_labor() -> dict:
    """Smart auto-allocation of the labor pool based on the realm's current needs."""
    return kingdom.auto_labor()


class CrewsBody(BaseModel):
    crews: list


@router.post("/crews")
def set_crews(body: CrewsBody) -> dict:
    """Replace the realm's named crews/teams with the ruler's edited list."""
    return kingdom.set_crews(body.crews)


class BuildBody(BaseModel):
    key: str


@router.post("/build")
def start_building(body: BuildBody) -> dict:
    return kingdom.start_building(body.key)


@router.post("/project-tick")
def project_tick() -> dict:
    return kingdom.tick_projects()


@router.get("/kingdom-chronicle")
def kingdom_chronicle(limit: int = 12) -> dict:
    return {"chronicle": state.recent_chronicle(limit=limit, tags=["kingdom"])}


class Bootstrap(BaseModel):
    location_name: str = "The Frontier Camp"
    region: str = "The Ashen Marches"


@router.post("/bootstrap")
def bootstrap(body: Bootstrap) -> dict:
    """Ensure a minimal origins-era starting place exists and is current."""
    world = state.get_world()
    if not world.get("location_id"):
        loc_id = "LOC-start"
        db.upsert("locations", {
            "id": loc_id, "name": body.location_name, "region": body.region,
            "discovered": 1, "danger_level": 2,
            "description": "A ragged cluster of tents and a half-built palisade on a "
                           "cold frontier. The first ember of something greater.",
        })
        state.update_world(location_id=loc_id)
    return {"world": state.get_world()}
