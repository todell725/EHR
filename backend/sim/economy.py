"""Optional always-on resource economy — the kingdom-phase heartbeat.

This is the *toggleable* half of the hybrid world model. It does nothing during the
origins era: it only runs once the player rules a domain (`found_domain`) AND the
toggle is on. Then a background loop advances the domain's economy every
`ECONOMY_TICK_SECONDS`, so the kingdom breathes on its own between play sessions.

Enable gates (all must hold):
  * world.domain_ruled is set (a domain exists), and
  * the toggle is on — either `ECONOMY_TICK_ENABLED=true` or the `economy_enabled`
    meta flag set by `found_domain(enable_economy=True)`.
"""

from __future__ import annotations

import logging

from backend.core import db, state
from backend.core.config import settings
from backend.sim import kingdom

logger = logging.getLogger("emberheart.economy")


def is_enabled() -> bool:
    if not state.get_world().get("domain_ruled"):
        return False
    if settings.economy_tick_enabled:
        return True
    row = db.query_one("SELECT value FROM meta WHERE key = 'economy_enabled'")
    return bool(row and row["value"] == "1")


def set_enabled(on: bool) -> None:
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('economy_enabled', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ["1" if on else "0"],
    )


def tick() -> dict | None:
    """Advance the domain economy one step. Returns a delta summary (or None)."""
    domain = kingdom.get_domain()
    if domain is None:
        return None

    pop = domain.get("population", 0)
    labor = domain.get("labor", {})
    stock = domain.setdefault("stockpiles", {})
    morale = domain.get("morale", 3)

    # Production scales with POPULATION via labor *fractions*. The old bug: a fixed founding
    # labor count that never grew, so a growing realm always out-ate its handful of farmers.
    total_labor = max(1, sum(int(v) for v in labor.values()))
    farm_frac = labor.get("farming", 0) / total_labor
    craft_frac = labor.get("craft", 0) / total_labor
    yield_mult = 0.9 + morale * 0.08          # morale 1..5 -> ~0.98 .. 1.30 (self-healing floor)

    # ONGOING building bonuses — read from the catalog's `ongoing` dict by what's actually built.
    # One-shot effects were already applied once on completion.
    built = domain.get("buildings", [])

    def _ongoing(stat: str) -> float:
        cat = kingdom.all_buildings()
        return sum(cat.get(b, {}).get("ongoing", {}).get(stat, 0) for b in built)

    food_cap_mult = _ongoing("food_cap_mult")          # granary
    craft_bonus = _ongoing("craft_bonus")              # workshop
    market_income = _ongoing("trade_income")            # market + wayfarer's hearth
    quarry_ore = _ongoing("quarry_ore")                # quarry works
    aquaculture_food = _ongoing("aquaculture_food")    # aquaculture pools
    herb_yield = _ongoing("herb_yield")                # herb gardens
    smokehouse_eff = _ongoing("smokehouse_eff")        # smokehouse
    brewery_morale = _ongoing("brewery_morale")        # brewery
    lumber_bonus = _ongoing("lumber_bonus")            # sawmill
    smelting_ore = _ongoing("smelting_ore")            # smelting hall
    beast_food = _ongoing("beast_food")                # beast pens
    pop_cap_bonus = _ongoing("pop_cap_bonus")          # ring-housing
    mender_soften = _ongoing("mender_soften")          # mender's clinic

    food_in = int(pop * farm_frac * 2.6 * yield_mult)
    food_in += int(pop * 0.05)                # the Flamekeeper's hearth-blessing — divine grace
    food_in += aquaculture_food
    food_in += beast_food
    food_in += int(herb_yield * 0.5)          # herbs supplement diet lightly

    ore_in = int(pop * craft_frac * 0.5 * yield_mult * (1 + craft_bonus))
    ore_in += quarry_ore
    ore_in += smelting_ore

    lumber_in = int(pop * craft_frac * 0.7 * yield_mult * (1 + craft_bonus))
    lumber_in += lumber_bonus

    # supplies = finished/worked goods: a trickle from craft labour + the manufacturing
    # buildings (weaver's guild, tannery, alchemist). Was previously never produced at all.
    supplies_in = int(pop * craft_frac * 0.10 * yield_mult * (1 + craft_bonus))
    supplies_in += _ongoing("supplies_out")

    # consumption: everyone eats one; the military draws upkeep
    food_out = pop
    upkeep = max(0, domain.get("military", 0) // 3)

    food_cap = int(pop * 6 * (1 + food_cap_mult))           # granary raises the hoard cap
    stock["food"] = min(food_cap, stock.get("food", 0) + food_in - food_out)
    stock["ore"] = stock.get("ore", 0) + ore_in
    stock["lumber"] = stock.get("lumber", 0) + lumber_in
    stock["supplies"] = stock.get("supplies", 0) + supplies_in

    # treasury: taxes scaled by morale, minus upkeep, plus market trade income
    taxes = int(pop * 0.1 * (0.5 + morale / 5))
    domain["treasury"] = domain.get("treasury", 0) + taxes + market_income - upkeep

    # morale + population drift — gentle, bounded, no death-spiral, no balloon
    # brewery and mender's clinic soften morale loss; mender_soften floors at 2
    morale_floor = 2 if mender_soften else 1
    if stock["food"] < 0:
        domain["morale"] = max(morale_floor, morale - 1)
        domain["population"] = max(1, pop - max(1, abs(stock["food"]) // 8))
        stock["food"] = 0
    elif stock["food"] > pop:                      # fed and comfortable
        if morale < 5:
            domain["morale"] = min(5, morale + 1 + brewery_morale)
        # housing is a real CEILING on population (not a per-tick brake). Grow at the
        # natural ~1.5%/tick up to however many beds the kingdom has.
        housing_cap = int(domain.get("housing_cap") or 0)
        if housing_cap <= 0:                       # fall back to building bonuses if unset
            housing_cap = pop + max(pop_cap_bonus, 1)
        if morale >= 4 and stock["food"] > pop * 2 and pop < housing_cap:
            domain["population"] = min(housing_cap, pop + max(1, pop // 65))

    kingdom.set_domain(domain)
    summary = {
        "food": stock["food"], "ore": stock["ore"], "lumber": stock["lumber"],
        "supplies": stock.get("supplies", 0),
        "treasury": domain["treasury"], "morale": domain["morale"],
        "population": domain["population"], "taxes": taxes, "upkeep": upkeep,
    }
    logger.info("economy tick: %s", summary)
    return summary
