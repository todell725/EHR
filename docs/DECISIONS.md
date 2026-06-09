# Decisions & Assumptions (review log)

Things I decided or assumed while building. Flagged so you can veto/tune any of them.

## Confirmed product decisions
- **LLM:** local Ollama only (free, self-owned, no content policy).
- **Interface:** web UI; the engine is API-first with the UI as a thin layer.
- **Canon:** *fresh reboot*. The existing `Claudes-EmberHeart` / `origins` corpus is
  ingested as **seed lore + foreshadowing**, never as authoritative starting state. The
  campaign arc deliberately runs **origins → kingdom-building**.
- **Ruleset:** existing **homebrew** (5e-derived core + RuneScape-style idle skills), not
  the 5e SRD.
- **World cadence:** **phased hybrid** — session/calendar-driven core always on; the
  always-on resource economy is built but **toggled OFF until a domain is ruled**.

## Homebrew ruleset assumptions (`backend/rules/homebrew.py`)
Grounded in `Claudes-EmberHeart/docs/PARTY_STATE.json` + the `*_DB.json` skill files.
- **A1.** Ability modifier = `(score - 10) // 2` (standard 5e).
- **A2.** Default proficiency follows the 5e level table, BUT a per-character stored
  `proficiency_bonus` always overrides it (the corpus uses non-standard values, e.g.
  Kaelrath = 3 @ L20).
- **A3.** Idle-skill XP uses the exact RuneScape curve, capped at level 99 (corpus skill
  levels like mining 32 sit comfortably inside this).
- **A4.** Character-level XP uses 5e milestone thresholds by default; the corpus diverges
  (522,225 XP @ L20), so **level-up is GM-confirmed, not auto-applied** — XP accrues and a
  level-up is *suggested*.
- **A5.** Difficulty→DC ladder is the 5e one (Very Easy 5 … Nearly Impossible 30).

These are all isolated in one file — change the numbers there and nothing else moves.

## Engineering assumptions
- **New-campaign state is created fresh**, not restored from the corpus. Ingestion only
  populates *semantic memory*; it does **not** create live PCs/NPCs/factions. (You build
  the cast via play + the GM panel. Pulling a specific corpus NPC into live play is a nice
  future button, not v1.)
- **Era tagging is keyword-based.** Chunks mentioning Golden-Age / post-scarcity /
  intergalactic markers are tagged `future_foreshadow` and excluded from normal retrieval
  (surfaced only when explicitly requested). The keyword list lives in `ingest/ingest.py`
  and is easy to extend if something leaks.
- **Quest ingestion is short-form** (title/desc/location/conclusion) — the 27k-line
  turn-by-turn bulk is intentionally skipped to keep the embedding set lean.
- **Streaming UX:** raw tokens stream live; on the final `result` event the UI snaps to the
  clean parsed narrative. Simpler and more robust than mid-stream section trimming.
- **Dice injection across turns:** a `ROLL_REQUEST` this turn is rolled by the engine and
  injected into the *next* prompt (persisted in `meta`), per the spec.

## Open items / things to confirm
- **Ingestion environment:** embedding needs Ollama + `nomic-embed-text`. If you run the
  app on funiserver but the corpus lives on your Mac, either run ingestion locally first,
  copy the seeded `data/emberheart.db` up, or mount the corpus into the container (see the
  commented volumes in `docker-compose.yml`). The app runs fine with **zero** seed memory.
- **funiserver port** is assumed `8000` — change in `.env` / compose if it clashes.
- **Narration model:** `.env.example` defaults to `llama3.1`; for richer prose pick a
  larger local model where hardware allows.
- **Faction/economy tuning:** the tick math (`sim/factions.py`, `sim/economy.py`) is a
  reasonable first pass — balance to taste once you're playing the kingdom phase.

## Deferred (spec extensibility hooks, not built)
Multiplayer PCs · TTS of narration · procedural map/image gen · Discord front-end. The
architecture leaves seams for each.
