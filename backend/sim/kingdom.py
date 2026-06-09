"""Kingdom-building — the back half of the origins -> kingdom arc.

Until the player rules a domain this lies dormant. `found_domain` flips the arc into
its kingdom phase, seeds a domain ledger, and (optionally) arms the always-on economy
tick. The domain ledger is small and lives in `meta` as JSON — no separate table
needed for v1.

Seasonal decision events (crop failure, border skirmish, trade proposal, grievance)
are the kingdom-scale equivalents of quests: they demand a player choice and react.
"""

from __future__ import annotations

import functools
import json
import random
import threading

from backend.core import db, state

DEFAULT_DOMAIN = {
    "name": "",
    "founded_year": 1,
    "population": 120,
    "treasury": 200,
    "military": 15,
    "morale": 3,        # 1..5
    "infrastructure": 1,
    "stockpiles": {"food": 40, "ore": 10, "lumber": 20},
    "labor": {"farming": 50, "military": 15, "craft": 20, "idle": 35},
    "buildings": [],
    "projects": [],
}

SEASONAL_EVENTS = [
    {"key": "crop_failure", "text": "Blight withers the fields — food stores will not last the season.",
     "effect": {"stockpiles.food": -20, "morale": -1}},
    {"key": "border_skirmish", "text": "Raiders test the borderlands; the militia musters.",
     "effect": {"military": -3, "treasury": -15}},
    {"key": "trade_proposal", "text": "A merchant guild proposes a trade compact on favorable terms.",
     "effect": {"treasury": +30}},
    {"key": "peasant_grievance", "text": "Commonfolk petition against the levies; unrest simmers.",
     "effect": {"morale": -1}},
    {"key": "good_harvest", "text": "A bountiful harvest fills the granaries.",
     "effect": {"stockpiles.food": +30, "morale": +1}},
]

# ------------------------------------------------------------------ buildings

BUILDINGS: dict[str, dict] = {
    # ── pre-existing (seeded on founding) ──
    "blood_wall": {
        "label": "The Geomantic Ring",
        "cost": {},
        "turns": 0,
        "effect": {"military": +2},
        "ongoing": {},
        "requires": [],
        "category": "defense",
        "desc": "15-ft black stone barrier mortared with Kaelrath's life.",
    },
    "ember_vault": {
        "label": "The Ember-Vault",
        "cost": {},
        "turns": 0,
        "effect": {"morale": +1},
        "ongoing": {},
        "requires": [],
        "category": "divine",
        "desc": "Underground vault housing the EmberHeart and Sol-Thairn.",
    },
    "god_forge": {
        "label": "The God-Forge",
        "cost": {},
        "turns": 0,
        "effect": {"morale": +1, "infrastructure": +1},
        "ongoing": {},
        "requires": [],
        "category": "divine",
        "desc": "The sprawling open-air stone smithy that never goes cold.",
    },
    # ── infrastructure ──
    "hearth_channels": {
        "label": "Hearth-Channels",
        "cost": {"lumber": 20, "ore": 5, "treasury": 30},
        "turns": 2,
        "effect": {"infrastructure": +1},
        "ongoing": {},
        "requires": [],
        "category": "infrastructure",
        "desc": "The geothermal distribution network.",
    },
    "ember_cisterns": {
        "label": "Ember Cisterns",
        "cost": {"lumber": 25, "ore": 10, "treasury": 40},
        "turns": 3,
        "effect": {"morale": +1},
        "ongoing": {"siege_resilience": 1},
        "requires": ["hearth_channels"],
        "category": "infrastructure",
        "desc": "Heated underground water reserves.",
    },
    "quarry_works": {
        "label": "Quarry Works",
        "cost": {"lumber": 15, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {"infrastructure": +1},
        "ongoing": {"quarry_ore": 2},
        "requires": [],
        "category": "infrastructure",
        "desc": "Extraction face, hauling ramps, block-cutting.",
    },
    # ── defense ──
    "ironwood_gatehouse": {
        "label": "The Ironwood Gatehouse",
        "cost": {"lumber": 30, "ore": 15, "treasury": 50},
        "turns": 3,
        "effect": {"military": +2},
        "ongoing": {},
        "requires": ["blood_wall"],
        "category": "defense",
        "desc": "Reinforced timber and iron primary entry.",
    },
    "wardens_redoubt": {
        "label": "The Warden's Redoubt",
        "cost": {"lumber": 35, "ore": 20, "treasury": 60},
        "turns": 3,
        "effect": {"military": +3},
        "ongoing": {},
        "requires": ["ironwood_gatehouse"],
        "category": "defense",
        "desc": "Command post and militia housing against the inner wall.",
    },
    "scouts_perches": {
        "label": "Scout's Perches",
        "cost": {"lumber": 25, "ore": 15, "treasury": 45},
        "turns": 2,
        "effect": {"military": +2},
        "ongoing": {},
        "requires": ["quarry_works"],
        "category": "defense",
        "desc": "Insulated stone watchtowers with archer slits.",
    },
    "sally_port": {
        "label": "The Sally Port",
        "cost": {"lumber": 20, "ore": 10, "treasury": 35},
        "turns": 2,
        "effect": {"military": +1},
        "ongoing": {},
        "requires": ["ironwood_gatehouse"],
        "category": "defense",
        "desc": "Narrow secondary gate hidden in the wall's curve.",
    },
    "void_ward_stones": {
        "label": "The Void-Ward Stones",
        "cost": {"lumber": 20, "ore": 25, "treasury": 55},
        "turns": 3,
        "effect": {"military": +2, "morale": +1},
        "ongoing": {},
        "requires": ["scouts_perches"],
        "category": "defense",
        "desc": "Rune-carved basalt markers beyond the wall.",
    },
    "signal_braziers": {
        "label": "Signal Braziers",
        "cost": {"lumber": 15, "ore": 10, "treasury": 40},
        "turns": 2,
        "effect": {"military": +2},
        "ongoing": {},
        "requires": ["scouts_perches", "void_ward_stones"],
        "category": "defense",
        "desc": "Wall-linked warning fires completing the early-warning network.",
    },
    # ── divine ──
    "ash_pit": {
        "label": "The Ash-Pit",
        "cost": {"lumber": 15, "ore": 5, "treasury": 25},
        "turns": 2,
        "effect": {"morale": +1},
        "ongoing": {},
        "requires": ["god_forge"],
        "category": "divine",
        "desc": "Sacred disposal for failed forgings and funeral pyres.",
    },
    "offering_steps": {
        "label": "The Offering Steps",
        "cost": {"lumber": 25, "ore": 15, "treasury": 45},
        "turns": 3,
        "effect": {"morale": +2},
        "ongoing": {},
        "requires": [],
        "category": "divine",
        "desc": "Broad stone stairway to the Ember-Vault.",
    },
    "pilgrims_court": {
        "label": "The Pilgrim's Court",
        "cost": {"lumber": 35, "ore": 20, "treasury": 65},
        "turns": 4,
        "effect": {"morale": +2, "infrastructure": +1},
        "ongoing": {},
        "requires": ["offering_steps"],
        "category": "divine",
        "desc": "Sheltered forecourt for supplicants and oath-taking.",
    },
    "shardwork": {
        "label": "The Shardwork",
        "cost": {"lumber": 30, "ore": 25, "treasury": 70},
        "turns": 4,
        "effect": {"infrastructure": +2},
        "ongoing": {"craft_bonus": 0.20},
        "requires": ["god_forge"],
        "category": "divine",
        "desc": "Dedicated ember-glass workshop for relics and armor.",
    },
    # ── leadership ──
    "hearth_hall": {
        "label": "The Hearth-Hall",
        "cost": {"lumber": 35, "ore": 15, "treasury": 60},
        "turns": 4,
        "effect": {"morale": +1, "treasury": +10},
        "ongoing": {"trade_income": 1},
        "requires": [],
        "category": "leadership",
        "desc": "Central gathering place and seat of the King and Queen.",
    },
    "loremaster_archive": {
        "label": "The Loremaster's Archive",
        "cost": {"lumber": 30, "ore": 20, "treasury": 55},
        "turns": 3,
        "effect": {"infrastructure": +1},
        "ongoing": {},
        "requires": ["quarry_works"],
        "category": "leadership",
        "desc": "Climate-controlled stone building for vellum and lore.",
    },
    "hearthkeepers_lodge": {
        "label": "The Hearthkeeper's Lodge",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 3,
        "effect": {"morale": +1},
        "ongoing": {"food_efficiency": 0.10},
        "requires": [],
        "category": "leadership",
        "desc": "Administrative centre for rationing supplies.",
    },
    "war_table": {
        "label": "The War Table",
        "cost": {"lumber": 20, "ore": 15, "treasury": 50},
        "turns": 3,
        "effect": {"military": +2},
        "ongoing": {},
        "requires": ["wardens_redoubt"],
        "category": "leadership",
        "desc": "Stone annexe with a carved relief map.",
    },
    "royal_quarters": {
        "label": "The Royal Quarters",
        "cost": {"lumber": 30, "ore": 15, "treasury": 55},
        "turns": 3,
        "effect": {"morale": +2},
        "ongoing": {},
        "requires": [],
        "category": "leadership",
        "desc": "The king and queen's private rooms above the Ember-Vault.",
    },
    # ── sustenance ──
    "grand_granaries": {
        "label": "The Grand Granaries",
        "cost": {"lumber": 30, "ore": 10, "treasury": 50},
        "turns": 3,
        "effect": {"stockpiles.food": +30},
        "ongoing": {"food_cap_mult": 0.40},
        "requires": ["quarry_works"],
        "category": "sustenance",
        "desc": "Fortified raised dry-stone silos.",
    },
    "aquaculture_basins": {
        "label": "Geothermal Aquaculture Basins",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 3,
        "effect": {},
        "ongoing": {"aquaculture_food": 5},
        "requires": ["hearth_channels"],
        "category": "sustenance",
        "desc": "Stone-lined indoor tanks heated by the EmberHeart.",
    },
    "greenhouses": {
        "label": "Hearth-Warmed Greenhouses",
        "cost": {"lumber": 20, "ore": 5, "treasury": 40},
        "turns": 2,
        "effect": {},
        "ongoing": {"herb_yield": 3},
        "requires": ["hearth_channels", "god_forge"],
        "category": "sustenance",
        "desc": "Glass and timber lean-tos for herbs and vegetables.",
    },
    "smokehouse": {
        "label": "The Hunter's Smokehouse",
        "cost": {"lumber": 20, "ore": 5, "treasury": 30},
        "turns": 2,
        "effect": {},
        "ongoing": {"smokehouse_eff": 0.15},
        "requires": [],
        "category": "sustenance",
        "desc": "Large curing shed for processing game.",
    },
    "root_cellar_network": {
        "label": "The Root Cellar Network",
        "cost": {"lumber": 15, "ore": 10, "treasury": 35},
        "turns": 2,
        "effect": {},
        "ongoing": {"root_cellar_soften": 1},
        "requires": [],
        "category": "sustenance",
        "desc": "Frost-cut tunnels for cold storage.",
    },
    "brewery": {
        "label": "The Brewery",
        "cost": {"lumber": 25, "ore": 10, "treasury": 50},
        "turns": 3,
        "effect": {"morale": +2},
        "ongoing": {"brewery_morale": 1},
        "requires": ["hearth_hall"],
        "category": "sustenance",
        "desc": "Communal ale and mead house.",
    },
    "sled_house": {
        "label": "The Sled House",
        "cost": {"lumber": 20, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {},
        "ongoing": {"sled_soften": 1},
        "requires": [],
        "category": "sustenance",
        "desc": "Frontier hauling and deep-cold logistics.",
    },
    # ── industry ──
    "carpenters_mill": {
        "label": "The Carpenter's Mill",
        "cost": {"lumber": 20, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {},
        "ongoing": {"lumber_bonus": 3},
        "requires": [],
        "category": "industry",
        "desc": "Wood processing, framing, furniture.",
    },
    "tannery": {
        "label": "The Tannery",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 3,
        "effect": {},
        "ongoing": {"supplies_out": 8},
        "requires": ["char_pit"],
        "category": "industry",
        "desc": "Boiling and tanning monster hides into armor.",
    },
    "masons_yard": {
        "label": "The Mason's Yard",
        "cost": {"lumber": 20, "ore": 15, "treasury": 40},
        "turns": 2,
        "effect": {"infrastructure": +1},
        "ongoing": {},
        "requires": ["quarry_works"],
        "category": "industry",
        "desc": "Hub for stonecraft and basalt block staging.",
    },
    "weavers_guild": {
        "label": "The Weaver's Guild",
        "cost": {"lumber": 20, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {"morale": +1},
        "ongoing": {"supplies_out": 12},
        "requires": [],
        "category": "industry",
        "desc": "Longhouse for spinning wool and winter clothing.",
    },
    "smelting_hall": {
        "label": "The Smelting Hall",
        "cost": {"lumber": 30, "ore": 20, "treasury": 60},
        "turns": 4,
        "effect": {},
        "ongoing": {"smelting_ore": 4},
        "requires": ["masons_yard"],
        "category": "industry",
        "desc": "Bulk ore smelting at scale.",
    },
    "stables_mews": {
        "label": "The Stables and Mews",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 2,
        "effect": {"military": +1},
        "ongoing": {},
        "requires": [],
        "category": "industry",
        "desc": "Housing for Cindermane and mounts.",
    },
    "beast_pens": {
        "label": "Beast Pens and Kennels",
        "cost": {"lumber": 20, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {},
        "ongoing": {"beast_food": 3},
        "requires": ["stables_mews"],
        "category": "industry",
        "desc": "Pack animals, hounds, and slaughter pens.",
    },
    "alchemists_den": {
        "label": "The Alchemist's Den",
        "cost": {"lumber": 25, "ore": 15, "treasury": 55},
        "turns": 3,
        "effect": {"infrastructure": +1},
        "ongoing": {"supplies_out": 6},
        "requires": ["menders_clinic"],
        "category": "industry",
        "desc": "Refining herbs and glands into tinctures.",
    },
    "char_pit": {
        "label": "The Char Pit",
        "cost": {"lumber": 15, "ore": 5, "treasury": 25},
        "turns": 2,
        "effect": {},
        "ongoing": {},
        "requires": ["ash_pit"],
        "category": "industry",
        "desc": "Produces fuel, tallow, candles, and waterproofing.",
    },
    # ── civilian ──
    "ring_housing": {
        "label": "The Ring-Housing",
        "cost": {"lumber": 30, "ore": 10, "treasury": 50},
        "turns": 3,
        "effect": {"morale": +1},
        "ongoing": {"pop_cap_bonus": 288},     # one district = 36 cabins * ~8 souls
        "requires": ["hearth_channels"],
        "category": "civilian",
        "desc": "Dense stone and timber homes heated by geothermal network.",
    },
    "menders_clinic": {
        "label": "The Mender's Clinic",
        "cost": {"lumber": 20, "ore": 10, "treasury": 40},
        "turns": 2,
        "effect": {},
        "ongoing": {"mender_soften": 1},
        "requires": [],
        "category": "civilian",
        "desc": "Sterile herbal medical ward for the sick and injured.",
    },
    "wayfarers_hearth": {
        "label": "The Wayfarer's Hearth",
        "cost": {"lumber": 20, "ore": 5, "treasury": 35},
        "turns": 2,
        "effect": {},
        "ongoing": {"trade_income": 1},
        "requires": [],
        "category": "civilian",
        "desc": "Secure communal bunkhouse for refugees and traders.",
    },
    "memorial_wall": {
        "label": "The Memorial Wall",
        "cost": {},
        "turns": 0,
        "effect": {"morale": +2},
        "ongoing": {},
        "requires": [],
        "category": "civilian",
        "desc": "A smooth section of the Blood-Wall carved with the names of the dead.",
        "auto_complete": "chronicle_count>=10",
    },
    "apprentice_hall": {
        "label": "The Apprentice Hall",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 3,
        "effect": {"infrastructure": +1},
        "ongoing": {},
        "requires": ["loremaster_archive"],
        "category": "civilian",
        "desc": "School and workshop for children and young adults.",
    },
    "bathhouse": {
        "label": "The Bathhouse",
        "cost": {"lumber": 25, "ore": 10, "treasury": 45},
        "turns": 3,
        "effect": {"morale": +2},
        "ongoing": {},
        "requires": ["hearth_channels", "ember_cisterns"],
        "category": "civilian",
        "desc": "Geothermally heated stone baths.",
    },
}


def get_domain() -> dict | None:
    row = db.query_one("SELECT value FROM meta WHERE key = 'domain'")
    return json.loads(row["value"]) if row else None


def set_domain(domain: dict) -> None:
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('domain', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [json.dumps(domain)],
    )


# All domain read-modify-writes serialize on this lock. The economy tick, per-beat
# project ticks, labor/crew edits, builds, invests, and the DM's KINGDOM_CHANGE all
# rewrite the same `meta.domain` JSON blob from different threads (background loops vs
# threadpool request handlers); without it, the slower writer clobbers the faster one.
DOMAIN_LOCK = threading.RLock()


def domain_locked(fn):
    """Run a domain read-modify-write atomically under DOMAIN_LOCK (re-entrant)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with DOMAIN_LOCK:
            return fn(*args, **kwargs)
    return wrapper


@domain_locked
def found_domain(name: str, *, enable_economy: bool = True) -> dict:
    """Flip the campaign into its kingdom-building phase."""
    world = state.get_world()
    domain = dict(DEFAULT_DOMAIN)
    domain["name"] = name
    domain["founded_year"] = world.get("year", 1)
    # Seed pre-existing buildings that are already built from day one
    domain["buildings"] = ["blood_wall", "ember_vault", "god_forge"]
    set_domain(domain)
    state.update_world(arc_phase="kingdom", domain_ruled=1)
    if enable_economy:
        db.execute(
            "INSERT INTO meta (key, value) VALUES ('economy_enabled', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = '1'"
        )
    state.add_chronicle(f"{name} is founded — the player takes up a crown of thorns.",
                        tags=["kingdom", "founding"])
    return domain


# which kingdom stockpile a gathered idle material feeds — the overlap of the two themes
_KINGDOM_BUCKET = {
    "wood": "lumber", "stone": "lumber",
    "raw_meat": "food", "cooked_meal": "food", "berries": "food", "raw_fish": "food",
    "herbs": "food", "hide": "food",
    "ore": "ore", "metal_bar": "ore",
}


def bucket_for(material: str) -> str:
    return _KINGDOM_BUCKET.get(state.normalize_material(material), "supplies")


@domain_locked
def invest_material(material: str, qty: int) -> dict:
    """Pour gathered idle stores into the realm's stockpiles — what you grind in the
    Idle tab becomes the kingdom's lumber, food, and ore."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom yet — found one first"}
    take = state.take_material(material, qty)  # atomic check-and-spend
    if take <= 0:
        return {"ok": False, "detail": "not enough in stores"}
    bucket = bucket_for(material)
    stock = domain.setdefault("stockpiles", {})
    stock[bucket] = stock.get(bucket, 0) + take
    set_domain(domain)
    return {"ok": True, "invested": take, "bucket": bucket, "domain": domain}


def _apply_effect(domain: dict, effect: dict) -> None:
    for path, delta in effect.items():
        if "." in path:
            grp, key = path.split(".", 1)
            domain.setdefault(grp, {})
            domain[grp][key] = domain[grp].get(key, 0) + delta
        else:
            domain[path] = domain.get(path, 0) + delta
    domain["morale"] = max(1, min(5, domain.get("morale", 3)))


@domain_locked
def seasonal_event() -> dict | None:
    """Roll one seasonal decision event and apply its baseline effect."""
    domain = get_domain()
    if domain is None:
        return None
    event = random.choice(SEASONAL_EVENTS)
    _apply_effect(domain, event["effect"])
    set_domain(domain)
    state.add_chronicle(f"[{domain['name']}] {event['text']}", tags=["kingdom", event["key"]])
    return event


# ------------------------------------------------------------------ labor

@domain_locked
def set_labor(labor: dict) -> dict:
    """Reallocate the kingdom's labor pool. Incoming values are merged onto the
    existing ledger (the UI sends only the categories that moved — a partial update
    must not erase the rest), clamped to non-negative, and scaled so the total never
    exceeds population."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    pop = domain.get("population", 0)
    clean = {k: max(0, int(v)) for k, v in (domain.get("labor") or {}).items()}
    clean.update({k: max(0, int(v)) for k, v in labor.items()})
    total = sum(clean.values())
    if total > pop:
        # scale down proportionally
        factor = pop / total
        clean = {k: max(0, int(v * factor)) for k, v in clean.items()}
    domain["labor"] = clean
    set_domain(domain)
    return {"ok": True, "labor": clean}


# ------------------------------------------------------------------ crews / teams
@domain_locked
def set_crews(crews: list) -> dict:
    """Replace the realm's named crews/teams (the player's per-crew headcount edits).
    Stored on the domain so the DM/council can SEE the player's allocations."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    clean = []
    for c in crews or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        clean.append({"name": name[:60], "size": max(0, int(c.get("size", 0) or 0)),
                      "role": (c.get("role") or "").strip()[:90]})
    domain["crews"] = clean
    set_domain(domain)
    return {"ok": True, "crews": clean}


@domain_locked
def add_crew(name: str, size: int = 0, role: str = "") -> dict:
    """Add or update a named crew (e.g. the council stands up a new team in-story)."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    crews = domain.get("crews", [])
    for c in crews:
        if c.get("name", "").strip().lower() == name.strip().lower():
            if size:
                c["size"] = max(0, int(size))
            if role:
                c["role"] = role.strip()[:90]
            break
    else:
        crews.append({"name": name.strip()[:60], "size": max(0, int(size or 0)),
                      "role": role.strip()[:90]})
    domain["crews"] = crews
    set_domain(domain)
    return {"ok": True, "crews": crews}


@domain_locked
def auto_labor() -> dict:
    """Smart labor auto-allocation — reads the realm's actual situation and prioritizes
    accordingly (food first, crafters when building or short on resources, a standing
    defense, minimal idle). Not a dumb even split. Applies and returns the allocation."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    pop = int(domain.get("population", 0))
    if pop <= 0:
        return {"ok": False, "detail": "no population to allocate"}
    stock = domain.get("stockpiles", {})
    food = int(stock.get("food", 0))
    lumber = int(stock.get("lumber", 0))
    ore = int(stock.get("ore", 0))
    building = bool(domain.get("projects"))

    # priority bands — food security trumps everything (starvation is the failure mode)
    if food < pop:                                  # famine / deficit -> emergency farming
        farm, craft, mil = 0.58, 0.15, 0.12
        why = "Food critically low — farmers prioritized to break the famine."
    elif food < pop * 3:                            # tight -> lean toward food
        farm, craft, mil = 0.46, 0.20, 0.14
        why = "Food stores tight — leaning into farming to build a buffer."
    elif building or lumber < 200 or ore < 100:     # comfortable + building/short on mats
        farm, craft, mil = 0.36, 0.32, 0.15
        why = "Fed and building — crafters boosted for construction and resources."
    else:                                           # prosperous -> growth + defense
        farm, craft, mil = 0.38, 0.22, 0.22
        why = "Prosperous — balanced for steady growth and a strong standing defense."

    labor = {
        "farming": int(pop * farm),
        "craft": int(pop * craft),
        "military": int(pop * mil),
    }
    labor["idle"] = max(0, pop - sum(labor.values()))   # remainder, exact total == pop
    domain["labor"] = labor
    set_domain(domain)
    return {"ok": True, "labor": labor, "rationale": why}


# ------------------------------------------------------------------ buildings / projects

def _can_afford(domain: dict, cost: dict) -> bool:
    stock = domain.get("stockpiles", {})
    for key, need in cost.items():
        if key == "treasury":
            if domain.get("treasury", 0) < need:
                return False
        else:
            if stock.get(key, 0) < need:
                return False
    return True


def _spend(domain: dict, cost: dict) -> None:
    stock = domain.setdefault("stockpiles", {})
    for key, need in cost.items():
        if key == "treasury":
            domain["treasury"] = domain.get("treasury", 0) - need
        else:
            stock[key] = stock.get(key, 0) - need


def _has_requirements(spec: dict, built: list[str]) -> bool:
    """Check if all prerequisite buildings are already built."""
    for req in spec.get("requires", []):
        if req not in built:
            return False
    return True


# --------------------------------------------------- dynamic / story-proposed catalog
def custom_buildings() -> dict:
    """Buildings proposed in-story (by the council/DM) — stored in meta and merged into
    the catalog so the Kingdom tab can actually build them alongside the static ones."""
    row = db.query_one("SELECT value FROM meta WHERE key = 'custom_buildings'")
    try:
        return json.loads(row["value"]) if row else {}
    except Exception:  # noqa: BLE001
        return {}


def all_buildings() -> dict:
    """The full buildable catalog: static BUILDINGS plus anything proposed in the story."""
    return {**BUILDINGS, **custom_buildings()}


@domain_locked
def add_building(label: str, *, key: str = "", category: str = "civilian", desc: str = "",
                 cost: dict | None = None, turns: int = 3, effect: dict | None = None,
                 ongoing: dict | None = None, requires: list | None = None,
                 upgrades_from: str = "") -> dict:
    """Register a building proposed in the story so it becomes buildable in the dashboard.
    If `upgrades_from` is set, completing it replaces that base building (an upgrade)."""
    import re

    if not key:
        key = "x_" + (re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "building")
    reqs = list(requires or [])
    if upgrades_from and upgrades_from not in reqs:
        reqs.append(upgrades_from)            # can't upgrade what isn't built
    spec = {
        "label": label, "category": category, "desc": desc or label,
        "cost": cost or {"lumber": 40, "ore": 20, "treasury": 60},
        "turns": int(turns), "effect": effect or {"infrastructure": 1},
        "ongoing": ongoing or {}, "requires": reqs, "proposed": True,
    }
    if upgrades_from:
        spec["upgrades_from"] = upgrades_from
    cb = custom_buildings()
    cb[key] = spec
    db.execute("INSERT INTO meta (key, value) VALUES ('custom_buildings', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", [json.dumps(cb)])
    return {"ok": True, "key": key, "spec": spec}


@domain_locked
def start_building(key: str) -> dict:
    """Begin construction of a building if affordable, not already built, and prerequisites met."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    cat = all_buildings()
    spec = cat.get(key)
    if spec is None:
        return {"ok": False, "detail": f"unknown building {key}"}
    built = domain.get("buildings", [])
    if key in built:
        return {"ok": False, "detail": f"{spec['label']} already built"}
    active = domain.get("projects", [])
    if any(p["key"] == key for p in active):
        return {"ok": False, "detail": f"{spec['label']} already under construction"}
    if not _has_requirements(spec, built):
        missing = [cat.get(r, {}).get("label", r) for r in spec.get("requires", []) if r not in built]
        return {"ok": False, "detail": f"needs: {', '.join(missing)}"}
    if not _can_afford(domain, spec["cost"]):
        return {"ok": False, "detail": "not enough resources"}
    _spend(domain, spec["cost"])
    active.append({"key": key, "label": spec["label"], "turns_total": spec["turns"], "turns_left": spec["turns"]})
    domain["projects"] = active
    set_domain(domain)
    state.add_chronicle(f"Construction begins: {spec['label']}.", tags=["kingdom", "build"])
    return {"ok": True, "project": active[-1], "domain": domain}


def _check_auto_buildings(domain: dict) -> list[str]:
    """Auto-complete buildings that meet their free unlock condition."""
    added = []
    built = domain.get("buildings", [])
    for key, spec in all_buildings().items():
        if key in built:
            continue
        auto = spec.get("auto_complete")
        if not auto:
            continue
        # only support chronicle_count>=N for now
        if auto.startswith("chronicle_count>="):
            threshold = int(auto.split(">=", 1)[1])
            if state.chronicle_count() >= threshold:
                built.append(key)
                _apply_effect(domain, spec.get("effect", {}))
                state.add_chronicle(f"{spec['label']} rises from memory — unlocked!", tags=["kingdom", "build"])
                added.append(key)
    if added:
        domain["buildings"] = built
    return added


@domain_locked
def tick_projects() -> dict:
    """Advance all active projects by one turn. Completed projects apply their
    permanent effect and move to the buildings list."""
    domain = get_domain()
    if domain is None:
        return {"ok": False, "detail": "no kingdom"}
    active = domain.get("projects", [])
    completed = []
    remaining = []
    for p in active:
        p["turns_left"] = max(0, p["turns_left"] - 1)
        if p["turns_left"] <= 0:
            completed.append(p)
        else:
            remaining.append(p)
    cat = all_buildings()
    built = domain.get("buildings", [])
    for p in completed:
        spec = cat.get(p["key"])
        if spec:
            base = spec.get("upgrades_from")    # an upgrade replaces the building it improves
            if base and base in built:
                built.remove(base)
            _apply_effect(domain, spec.get("effect", {}))
            state.add_chronicle(f"{spec['label']} completed!", tags=["kingdom", "build"])
    built.extend([p["key"] for p in completed])
    domain["buildings"] = built
    domain["projects"] = remaining
    _check_auto_buildings(domain)
    set_domain(domain)
    return {"ok": True, "completed": completed, "remaining": remaining, "domain": domain}


def get_buildings() -> list[dict]:
    """Return the list of built structures with their specs."""
    domain = get_domain()
    if domain is None:
        return []
    cat = all_buildings()
    return [cat[k] for k in domain.get("buildings", []) if k in cat]


def get_projects() -> list[dict]:
    """Return active construction projects."""
    domain = get_domain()
    if domain is None:
        return []
    return domain.get("projects", [])


# ------------------------------------------------------------------ summary

def get_summary() -> dict | None:
    """Full kingdom snapshot for the dashboard."""
    domain = get_domain()
    if domain is None:
        return None
    return {
        "domain": domain,
        "buildings": get_buildings(),
        "projects": get_projects(),
        "catalog": all_buildings(),
        "labor_total": domain.get("population", 0),
    }
