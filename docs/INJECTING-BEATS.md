# Reading & Injecting Beats (post-migration)

How to read what's happening in the live game and push hand-authored DM beats
(montages, scenes, cinematic turns) into the feed — **with their state changes
applied** — now that the canonical save lives on funiserver, not the Mac.

## TL;DR

- **Live server:** `http://100.114.116.111:8000` (funiserver, tailnet). Reachable
  over the tailnet; no SSH needed for normal beat work.
- **Read a beat:** `GET /api/play/state`
- **Inject a beat:** `POST /api/play/inject` with an `InjectBeat` body — and put
  any real state changes in the `mechanics` field so prose and ledger can't desync.
- **The canonical DB is on funiserver** (`…/data/emberheart.db`). Do **not** write
  the Mac DB — it's only a backup and the game ignores it. All state changes go
  through the inject `mechanics` path (HTTP), not direct DB writes.

> **Why this replaced the old workflow:** pre-migration we did direct `state.*` DB
> writes on the Mac *then* posted prose. That DB is no longer the live one. The
> inject endpoint now carries validated `mechanics` (applied through the same
> `apply_mechanics` trust boundary a model turn uses), so a single HTTP call does
> both the prose and the real state — no SSH, no split-brain.

---

## 1. Read the current beat

```bash
curl -s http://100.114.116.111:8000/api/play/state | python3 -m json.tool
```

Response shape:

```jsonc
{
  "current": { "seq": ..., "status": "done|running", "action": "..." },
  "last": {
    "action": "<what the player did>",
    "result": {
      "turn": 581,
      "narrative": "<the DM prose>",
      "suggestions": [ { "text": "...", "requires_roll": false } ],
      "chronicle": "<one-line chronicle beat>",
      "applied": [ "..." ],        // state changes that landed
      "rejected": [], "notes": [],
      "model": "deepseek-v4-pro:cloud",
      "seq": ...
    }
  }
}
```

- `last.result.narrative` = the last thing the player saw.
- `last.action` = the last thing the player did.
- If `current.status == "running"`, a live turn is in flight — **don't inject over
  it**; wait for `done`.

For deeper context (chronicle history, hooks, NPCs) hit the read endpoints, e.g.
`GET /api/quests`, `GET /api/world`, `GET /api/journal`, `GET /api/ascension`.

---

## 2. Inject a beat

`POST /api/play/inject` with body (`InjectBeat`, all fields except `narrative`
optional):

| field         | type            | purpose |
|---------------|-----------------|---------|
| `narrative`   | `str`           | the prose shown as a Chronicle Weaver turn |
| `suggestions` | `list[dict]`    | next-action chips: `{"text": "...", "requires_roll": false, "roll_hint": null}` |
| `applied`     | `list[str]`     | free-text "what happened" chips (display only) |
| `mechanics`   | `list[str]`     | **`TAG: args` lines — the REAL state changes**, applied server-side |

Put every real change in `mechanics`. They run through `apply_mechanics`, so a
typo'd tag is rejected/noted (and surfaced in the returned `applied`) instead of
silently wrong. The endpoint returns `{"ok": true, "seq": <n>}`.

### Minimal example

```bash
curl -s -X POST http://100.114.116.111:8000/api/play/inject \
  -H 'Content-Type: application/json' \
  -d '{
    "narrative": "The God-Forge cools. Heartfire lies finished on the anvil...",
    "mechanics": [
      "ITEM_ADD: Kaelrath, Heartfire (divine-steel blade)",
      "AWARD_XP: Kaelrath, 500",
      "JOURNAL: triumphant, The blade is named and the people are in it."
    ],
    "suggestions": [
      {"text": "Raise Heartfire before the council", "requires_roll": false}
    ],
    "applied": ["Heartfire forged"]
  }'
```

### Authoring with a script (preferred for multi-step montages)

For anything bigger than a one-liner, write a throwaway Python script that builds
the payload and POSTs it. Keeps the prose readable and the mechanics list reviewable
before you fire it.

```python
import requests, json

BASE = "http://100.114.116.111:8000"

beat = {
    "narrative": (
        "Three weeks folded into a single breath of montage...\n\n"
        "..."
    ),
    "mechanics": [
        "TIME_ADVANCE: 21",
        "MATERIAL_GAIN: obsidian_steel, 1",
        "KINGDOM_CHANGE: morale, +1",
        "CHRONICLE intentionally omitted — narrative carries it",  # NOTE: not a tag; will be 'noted'
    ],
    "suggestions": [
        {"text": "Descend into the Sunken Caldera", "requires_roll": False},
    ],
    "applied": ["3-week montage"],
}

r = requests.post(f"{BASE}/api/play/inject", json=beat, timeout=15)
print(r.status_code, r.json())   # check 'applied' for ⚠ rejected / note: lines
```

**Always check the response's `applied` list** for `⚠ rejected:` or `note:` lines —
that's how a malformed tag surfaces. Fix and re-inject if a change didn't land.

---

## 3. Canonical mechanics tags

These dispatch directly in `apply_mechanics`. ~70 invented synonyms also alias onto
them (e.g. `DAMAGE`→`HP_CHANGE`, `LOOT`/`GAIN_ITEM`→`ITEM_ADD`, `RECRUIT`→`PARTY_JOIN`,
`GRANT_XP`/`AWARD_XP`→`XP_GRANT`), and anything unrecognized is soft-noted, not
crashed. Prefer the canonical name.

| Category | Tags | Args |
|----------|------|------|
| HP        | `HP_CHANGE` | `<pc>, <±n>` |
| XP        | `XP_GRANT`, `SKILL_XP` | `<pc>, <n>` / `<pc>, <skill>, <n>` |
| Rolls     | `ROLL_REQUEST`, `SAVE_REQUEST` | `<pc>, <skill/ability>, <DC?>` |
| Conditions| `CONDITION_ADD`, `CONDITION_REMOVE` | `<pc>, <condition>, <duration?>` |
| Items     | `ITEM_ADD`, `ITEM_REMOVE` | `<pc>, <item>, <qty?>` |
| NPCs      | `NPC_SPAWN`, `NPC_STATUS`, `NPC_DISPOSITION_CHANGE`, `PARTY_JOIN` | `<name>, …` |
| Factions  | `FACTION_REP_CHANGE` | `<faction>, <±n>` |
| Quests    | `QUEST_ADD`, `QUEST_UPDATE`, `QUEST_COMPLETE` | `<title>, …` |
| World     | `WORLD_HOOK`, `HOOK_RESOLVE`, `WORLD_EVENT`, `SCENE_SET`, `TIME_ADVANCE` | varies |
| Reflective| `JOURNAL` | `<mood>, <reflection>` |
| Materials | `MATERIAL_GAIN`, `MATERIAL_SPEND` | `<material>, <qty>` |
| Kingdom   | `KINGDOM_CHANGE` | `<stat>, <±n>` (stat ∈ morale/treasury/military/population/infrastructure/food/…) |
| Buildings | `BUILDING_ADD`, `BUILDING_PROPOSE` | `<name>, <category?>` |
| Crews     | `CREW_SET` | `<name>, <size?>, <role?>` |
| Combat    | `COMBAT_START`, `COMBAT_END`, `ENEMY_HP`, … | see `mechanics.py` |

> Tag args are comma-split. The comma-split bug class has bitten multi-word args
> before (`ITEM_ADD`/`WORLD_HOOK` rejoin now; `CONDITION_ADD` is still partly
> vulnerable). Keep condition/item names simple, or verify in the response.

Authoritative list lives in [`backend/dm/mechanics.py`](../backend/dm/mechanics.py)
(`apply_mechanics` dispatch + `_ALIASES`).

---

## 4. Rules of thumb

- **Don't inject over a running turn.** Check `current.status == "done"` first.
- **Don't write the Mac DB.** It's a backup; the game reads funiserver's copy.
- **State always goes in `mechanics`**, never as a separate DB write — that's the
  whole point of the migration-safe path (no split-brain).
- **Read the response.** `applied` shows what really landed, including
  `⚠ rejected` / `note:` for anything fishy.
- **The feed is DB-backed** (`meta.feed_recent`) — injected beats survive restarts
  now. (Historical gotcha: if re-pushing a beat lost to an old build, re-inject
  *after* the deploy that added persistence.)
- **Nudge the DM live** (don't author it yourself) with `POST /api/play/submit`
  `{"text": "...", "pc_id": "..."}` — that enqueues a real model turn that streams
  to the feed, instead of an authored inject.
