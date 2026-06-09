"""Idle skilling — gather → process production chains with real resource dependencies.

You set ONE active activity. It runs on a server-side tick (so it accumulates even while
the app is closed), gated by two things: your hero's **skill level** for that activity, and
its **input materials**. Gathering (woodcutting, hunting, mining, foraging, fishing) needs
no inputs; processing needs the right raw goods — you can't cook without meat AND wood,
can't smith without ore AND fuel, can't craft without leather AND fiber. Each cycle yields
materials into a shared stockpile and grants idle-skill XP to the hero (levels real skills).

Offline progress is capped so leaving it overnight doesn't dump a mountain of loot.
"""

from __future__ import annotations

import json
import logging
import time

from backend.core import db, state

logger = logging.getLogger("emberheart.idle")

OFFLINE_CAP_SECONDS = 4 * 3600  # at most 4 hours of catch-up per tick

# activity -> {skill, min_level, seconds/cycle, xp/cycle, inputs{mat:qty}, outputs{mat:rate}}
ACTIVITIES: dict[str, dict] = {
    # --- gathering (no inputs) ---
    "woodcutting": {"skill": "woodcutting", "min_level": 1, "seconds": 6, "xp": 8,
                    "inputs": {}, "outputs": {"wood": 1.0}},
    "foraging":    {"skill": "foraging", "min_level": 1, "seconds": 7, "xp": 9,
                    "inputs": {}, "outputs": {"herbs": 0.6, "plant_fiber": 0.8, "berries": 0.5}},
    "hunting":     {"skill": "hunting", "min_level": 1, "seconds": 8, "xp": 12,
                    "inputs": {}, "outputs": {"raw_meat": 1.0, "hide": 0.4}},
    "fishing":     {"skill": "fishing", "min_level": 1, "seconds": 7, "xp": 10,
                    "inputs": {}, "outputs": {"raw_fish": 1.0}},
    "mining":      {"skill": "mining", "min_level": 1, "seconds": 8, "xp": 11,
                    "inputs": {}, "outputs": {"ore": 0.8, "stone": 0.5}},
    # --- processing (need inputs from gathering) ---
    "cooking":     {"skill": "cooking", "min_level": 1, "seconds": 6, "xp": 10,
                    "inputs": {"raw_meat": 1, "wood": 1}, "outputs": {"cooked_meal": 1.0}},
    "tanning":     {"skill": "leatherworking", "min_level": 1, "seconds": 7, "xp": 9,
                    "inputs": {"hide": 1}, "outputs": {"leather": 1.0}},
    "smithing":    {"skill": "smithing", "min_level": 5, "seconds": 10, "xp": 16,
                    "inputs": {"ore": 2, "wood": 1}, "outputs": {"metal_bar": 1.0}},
    "crafting":    {"skill": "crafting", "min_level": 3, "seconds": 9, "xp": 13,
                    "inputs": {"leather": 1, "plant_fiber": 2}, "outputs": {"supplies": 1.0}},
}


# ----------------------------------------------------------------- meta storage
def _materials() -> dict:
    row = db.query_one("SELECT value FROM meta WHERE key = 'idle_materials'")
    return json.loads(row["value"]) if row else {}


def _save_materials(m: dict) -> None:
    db.execute("INSERT INTO meta (key, value) VALUES ('idle_materials', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", [json.dumps(m)])


def _idle() -> dict:
    row = db.query_one("SELECT value FROM meta WHERE key = 'idle'")
    return json.loads(row["value"]) if row else {"active": None, "last_tick": time.time()}


def _save_idle(s: dict) -> None:
    db.execute("INSERT INTO meta (key, value) VALUES ('idle', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", [json.dumps(s)])


def _hero() -> dict | None:
    h = state.heroes()
    return h[0] if h else None


# --------------------------------------------------------------------- the tick
def tick(now: float | None = None) -> dict | None:
    """Advance the active activity by however many whole cycles fit since last tick,
    gated by skill level and input materials. Called by the loop and on every view."""
    now = now or time.time()
    s = _idle()
    active = s.get("active")
    last = s.get("last_tick", now)

    if not active or active not in ACTIVITIES:
        s["last_tick"] = now
        _save_idle(s)
        return None

    spec = ACTIVITIES[active]
    elapsed = min(now - last, OFFLINE_CAP_SECONDS)
    cycles = int(elapsed // spec["seconds"])
    if cycles <= 0:
        return None

    hero = _hero()
    level = int((hero.get("skills") or {}).get(spec["skill"], 1)) if hero else 1
    if level < spec["min_level"]:
        s["last_tick"] = now
        _save_idle(s)
        return {"stalled": f"need {spec['skill']} level {spec['min_level']}"}

    # gate by inputs AND apply the spend/produce atomically under the shared material
    # lock, re-reading inside the lock — otherwise a concurrent deposit/spend gets
    # clobbered when we write back a stale snapshot (the "nothing ever depletes" dupe).
    gained: dict = {}
    with state.MATERIAL_LOCK:
        mats = _materials()
        if spec["inputs"]:
            cap = min(int(mats.get(k, 0) // v) for k, v in spec["inputs"].items())
            cycles = min(cycles, cap)
        if cycles <= 0:
            s["last_tick"] = now
            _save_idle(s)
            missing = ", ".join(k for k, v in spec["inputs"].items() if mats.get(k, 0) < v)
            return {"stalled": f"out of {missing}"}
        for k, v in spec["inputs"].items():
            mats[k] = mats.get(k, 0) - v * cycles
        for k, rate in spec["outputs"].items():
            q = int(cycles * rate)
            if q > 0:
                mats[k] = mats.get(k, 0) + q
                gained[k] = q
        _save_materials(mats)

    leveled = None
    if hero:
        r = state.grant_skill_xp(hero["id"], spec["skill"], spec["xp"] * cycles)
        if r and r.get("leveled"):
            # skill levels auto-apply (no GM queue); surface them so idle progress is felt,
            # not silent — one beat per level crossed (naturally deduped: leveled is one-shot)
            leveled = {"skill": r["skill"], "level": r["level"]}
            state.add_chronicle(f"{hero['name']}'s {r['skill']} reached level {r['level']}.",
                                tags=["idle", "skill", "level-up"], significant=False)

    s["last_tick"] = last + cycles * spec["seconds"]  # carry leftover sub-cycle time
    _save_idle(s)
    return {"cycles": cycles, "gained": gained, "leveled": leveled}


# ------------------------------------------------------------------- public api
def set_active(activity: str | None) -> dict:
    tick()  # settle the current activity before switching
    if activity and activity not in ACTIVITIES:
        return get_state()
    s = _idle()
    s["active"] = activity
    s["last_tick"] = time.time()
    _save_idle(s)
    return get_state()


def deposit_to_inventory(material: str, qty: int) -> dict:
    """Move gathered stores out of the larder and onto the hero's character sheet as a
    usable inventory item (so what you grind in the Idle tab can be carried into the story)."""
    tick()
    key = state.normalize_material(material)
    have = int(_materials().get(key, 0))
    take = max(0, min(int(qty), have))
    if take <= 0:
        return {"ok": False, "detail": "not enough in stores", **get_state()}
    state.adjust_material(key, -take)
    hero = _hero()
    if hero:
        label = key.replace("_", " ").title()
        inv = list(hero.get("inventory") or [])
        for it in inv:
            if it.get("item", "").lower() == label.lower():
                it["qty"] = it.get("qty", 1) + take
                break
        else:
            inv.append({"item": label, "qty": take})
        state.upsert_pc({"id": hero["id"], "inventory": inv})
    return {"ok": True, "deposited": take, "material": key, **get_state()}


def get_state() -> dict:
    tick()  # catch up so the view is current
    s = _idle()
    mats = {k: int(v) for k, v in _materials().items() if v}
    hero = _hero()
    skills = (hero.get("skills") or {}) if hero else {}
    activities = []
    for name, spec in ACTIVITIES.items():
        lvl = int(skills.get(spec["skill"], 1))
        activities.append({
            "name": name, "skill": spec["skill"], "min_level": spec["min_level"],
            "level": lvl, "unlocked": lvl >= spec["min_level"],
            "inputs": spec["inputs"], "outputs": list(spec["outputs"].keys()),
            "active": s.get("active") == name,
        })
    return {"active": s.get("active"), "materials": mats, "activities": activities}
