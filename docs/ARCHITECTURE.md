# Architecture

EmberHeart Reborn is a FastAPI engine that fuses a **DM orchestrator**, a **world
simulation**, and a **three-layer memory** stack behind one HTTP/WS surface, backed by a
single SQLite file. The web UI is no-build Preact served as static assets.

```
                       ┌───────────────────────────────────────────┐
   Web UI (Preact)  ─► │  FastAPI  (backend/main.py + api/*)        │
   WS /api/play/ws     └───────────────┬───────────────────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │   DM Orchestrator (dm/)    │
                         │   stream → parse → apply   │
                         └───┬───────┬───────┬────────┘
            working memory   │       │       │  semantic recall (rag)
        (memory/working.py)  │       │       └────────────► memory_chunks (vectors)
                             │       │
                 prompt ◄────┘       └────► mechanics ─► structured state (core/state.py)
             (dm/prompt.py)               (dm/mechanics)     + dice (rules/)
                             │
                       Ollama /v1  (llm/client.py)         World sim (sim/): calendar,
                                                           factions, kingdom, economy, combat
```

## The three-layer memory stack

1. **Working memory** (`memory/working.py`) — ephemeral. Rebuilt every turn from
   structured state: location, in-world time, NPCs present, PC sheets, last few beats.
2. **Semantic memory / RAG** (`memory/rag.py`) — durable. Text chunks embedded by a
   fixed local model (`nomic-embed-text`), stored as float32 BLOBs in `memory_chunks`,
   retrieved by brute-force cosine in numpy. A relevance threshold drops weak matches so
   we inject signal, not noise. Play writes back here (chronicle beats, consolidations).
3. **Structured state** (`core/state.py` over `core/schema.sql`) — the ground truth. The
   LLM **reads** it (via the prompt) but **never writes** it. Only `dm/mechanics.py`
   mutates it, from parsed `[MECHANICS]` directives.

## The turn loop (`dm/orchestrator.py`)

1. bump the turn counter; load **dice rolled last turn** (injected into this prompt);
2. **retrieve** relevant memories; **route** to relevant NPCs; build the **working** block;
3. assemble system prompt (`dm/prompt.py`) + per-turn user block; call Ollama (hot temp),
   **streaming** raw tokens to the UI;
4. **parse** the four-section contract (`dm/parser.py`); if it fails, one **cold retry**;
5. **apply** `[MECHANICS]` deterministically (`dm/mechanics.py`), rolling any new dice;
6. write the `[CHRONICLE]` beat into structured state **and** semantic memory;
7. save this turn's rolls as "pending" for next turn; **consolidate** every N turns.

## Output contract

Every DM response must contain, in order:

- `[NARRATIVE]` — second-person prose (streamed live);
- `[MECHANICS]` — machine tags only (`HP_CHANGE`, `ROLL_REQUEST`, `FACTION_REP_CHANGE`,
  `WORLD_HOOK`, `COMBAT_START`, …) — applied to state;
- `[SUGGESTIONS]` — three options, each flagged `(requires roll: YES/NO)`;
- `[CHRONICLE]` — one terse log line, or `none`.

The parser is tolerant (markdown bold, casing) and reports `parse_ok` so the orchestrator
can retry. The LLM declares; the engine enforces. **The LLM never rolls dice.**

## World simulation (`sim/`)

- **calendar.py** — four 90-day seasons; `advance(amount, unit)` moves the clock and fires
  due scheduled events / quest deadlines.
- **factions.py** — each faction makes one tier-appropriate move per session tick.
- **kingdom.py** — dormant until `found_domain` flips the arc to its kingdom phase; then a
  small domain ledger (population/treasury/military/morale/stockpiles) + seasonal events.
- **economy.py** — the **optional** always-on resource tick. Gated: runs only when a
  domain is ruled *and* the toggle is on. This is the "phased hybrid" world model.
- **combat.py** — initiative, abstract zones, enemy-AI profiles, and death saves; the DM
  narrates over a Python-resolved log.

## Why these choices

- **SQLite + numpy** over a vector DB: the corpus is well under 10k chunks; a server would
  be pure overhead. One file holds state + memory + vectors.
- **Ollama OpenAI `/v1`**: standard client, easy model swaps, local + free, no content
  policy (suits mature campaign content).
- **No-build frontend**: Preact + htm from a CDN — zero toolchain, matches the lean-tooling
  preference.
