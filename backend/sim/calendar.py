"""In-world calendar — the clock the living world runs on.

Time advances from player actions (the DM emits `TIME_ADVANCE`). When the date
crosses a scheduled deadline, the event fires automatically: quests expire, sieges
land, NPCs act. This is the spine of "the world does not pause when the player rests."

Homebrew calendar: four 90-day seasons (a 360-day year), six slots per day.
"""

from __future__ import annotations

import json

from backend.core import db, state

SEASONS = ["The Sowing", "The Long Light", "The Withering", "The Frost"]
DAYS_PER_SEASON = 90
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
TIMES_OF_DAY = ["dawn", "morning", "midday", "afternoon", "evening", "night"]


def _season_index(name: str) -> int:
    try:
        return SEASONS.index(name)
    except ValueError:
        return 0


def now_ordinal(world: dict | None = None) -> int:
    """Absolute day count since the start of the campaign."""
    w = world or state.get_world()
    return (
        (int(w.get("year", 1)) - 1) * DAYS_PER_YEAR
        + _season_index(w.get("season", SEASONS[0])) * DAYS_PER_SEASON
        + (int(w.get("day", 1)) - 1)
    )


def _from_ordinal(ordinal: int) -> tuple[int, str, int]:
    ordinal = max(0, ordinal)
    year = ordinal // DAYS_PER_YEAR + 1
    rem = ordinal % DAYS_PER_YEAR
    season = SEASONS[rem // DAYS_PER_SEASON]
    day = rem % DAYS_PER_SEASON + 1
    return year, season, day


def advance(amount: int, unit: str = "hours") -> list[str]:
    """Advance the clock and return any events that fired."""
    w = state.get_world()
    unit = unit.lower().rstrip("s")  # tolerate 'hours'/'hour'

    time_idx = TIMES_OF_DAY.index(w.get("time_of_day", "morning")) \
        if w.get("time_of_day") in TIMES_OF_DAY else 1
    days_delta = 0

    if unit == "hour":
        slots = round(amount / 4)  # ~4 in-world hours per slot
        total = time_idx + slots
        time_idx = total % len(TIMES_OF_DAY)
        days_delta = total // len(TIMES_OF_DAY)
    elif unit == "day":
        days_delta = amount
    elif unit == "week":
        days_delta = amount * 7
    elif unit == "month":
        days_delta = amount * 30
    elif unit == "season":
        days_delta = amount * DAYS_PER_SEASON
    elif unit == "year":
        days_delta = amount * DAYS_PER_YEAR
    else:
        days_delta = amount  # default: treat as days

    new_ord = now_ordinal(w) + days_delta
    year, season, day = _from_ordinal(new_ord)
    state.update_world(year=year, season=season, day=day,
                       time_of_day=TIMES_OF_DAY[time_idx])

    return fire_due(new_ord)


# ------------------------------------------------------------- scheduled events
def schedule_event(at_ordinal: int, text: str) -> None:
    row = db.query_one("SELECT value FROM meta WHERE key = 'scheduled_events'")
    events = json.loads(row["value"]) if row else []
    events.append({"ordinal": at_ordinal, "text": text})
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('scheduled_events', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [json.dumps(events)],
    )


def schedule_in(days: int, text: str) -> None:
    schedule_event(now_ordinal() + days, text)


def fire_due(now_ord: int | None = None) -> list[str]:
    now_ord = now_ordinal() if now_ord is None else now_ord
    fired: list[str] = []

    # scheduled world events
    row = db.query_one("SELECT value FROM meta WHERE key = 'scheduled_events'")
    if row:
        events = json.loads(row["value"])
        keep, due = [], []
        for e in events:
            (due if e["ordinal"] <= now_ord else keep).append(e)
        for e in due:
            fired.append(e["text"])
            state.add_chronicle(e["text"], tags=["scheduled"], significant=True)
        if due:
            db.execute("UPDATE meta SET value = ? WHERE key = 'scheduled_events'",
                       [json.dumps(keep)])

    # quest deadlines (integer day-ordinal strings)
    for q in state.list_quests(status="active"):
        dl = q.get("deadline")
        if dl and str(dl).lstrip("-").isdigit() and int(dl) <= now_ord:
            state.upsert_quest({"id": q["id"], "status": "failed"})
            msg = f"Quest expired: {q['title']}."
            fired.append(msg)
            state.add_chronicle(msg, tags=["quest", "expired"])

    return fired
