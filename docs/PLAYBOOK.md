# PLAYBOOK — how to run and play EmberHeart Reborn

## First run
```bash
cp .env.example .env                     # set NARRATION_MODEL to a model you have
ollama pull nomic-embed-text             # embeddings (required for memory)
python -m backend.ingest.ingest          # optional: seed lore into memory
python -m backend.main                   # http://localhost:8000
```
Then in the UI: **GM → Bootstrap start**, **GM → New hero**, **▶ Start session**, and type.

## Playing
- Type an action; narration streams in, then snaps to the parsed beat with any dice and
  state changes. Click a **suggestion** to take it.
- **Dice are the engine's.** When an outcome is uncertain the DM requests a roll; the
  result is rolled in Python and folded into the next beat.
- **The world moves on its own.** Time advances when the DM narrates it; scheduled events
  fire on their day; factions act at each session start.

## Safety net (you can't lose your campaign)
- Every turn is snapshotted *before* it runs. **GM → ↶ Undo last turn** rolls back; press
  again to step further (15 deep).
- **Start session** auto-backs-up. **GM → Backup** / **Export DB** make durable copies.
- Backups live in `data/backups/`, undo snapshots in `data/snapshots/`.

## Combat
- The DM starts fights in the story by emitting `COMBAT_START: Frost Wolf x2 hp7 ac13 ai:tactical`.
- The **Combat** tab shows the encounter, HP, conditions, and log. Enemy turns and death
  saves resolve automatically after each of your actions.
- Enemy AI profiles: `berserker` (charges the strongest), `tactical` (focuses the weakest),
  `cowardly` (flees when bloodied), `spellcaster` (opens with control).

## The DM's tag vocabulary (for reference)
`HP_CHANGE · ENEMY_HP · ROLL_REQUEST · SAVE_REQUEST · CONDITION_ADD/REMOVE ·
ITEM_ADD/REMOVE · XP_GRANT · NPC_DISPOSITION_CHANGE · FACTION_REP_CHANGE · QUEST_ADD/UPDATE ·
WORLD_HOOK · WORLD_EVENT · NPC_SPAWN · NPC_STATUS · TIME_ADVANCE · COMBAT_START/END`
Unknown or malformed tags are rejected (shown as ⨯ on the beat), never half-applied.

## Tuning knobs (.env)
- `STRICT_OUTPUT=true` — switch from streamed bracket-sections to a buffered, guaranteed-
  parseable JSON contract. Use if a model keeps drifting from the format.
- `RAG_RELEVANCE_THRESHOLD` — raise to inject less (but more relevant) memory.
- `CONSOLIDATE_EVERY_TURNS` — how often play is compressed into long-term memory.
- For mature/romance content, set `NARRATION_MODEL` to an uncensored local model.

## Reliability check (run after changing the prompt or model)
```bash
PYTHONPATH=. ./.venv/bin/python scripts/playthrough.py --turns 30
```
Drives canned actions through the real DM and reports contract-adherence + state-integrity;
exits non-zero if it regresses.
