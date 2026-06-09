# EmberHeart Reborn — the Chronicle Weaver

A specialized, self-owned **AI Dungeon Master** for a long-running EmberHeart campaign.
It runs entirely on a local **Ollama** model, remembers the campaign through a
three-layer **RAG memory** stack, adjudicates a **homebrew ruleset** with deterministic
dice, and simulates a **living world** that grows from a dark *origins* era into full
**kingdom-building**.

> Fresh reboot. The grand god-king "golden age" of the old corpus is only distant
> prophecy here — ingested as *foreshadowing*, never as the starting state.

---

## Quickstart (local dev)

```bash
cd EmberHeartReborn
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit if your Ollama isn't on localhost:11434

# pull the models you configured (examples)
ollama pull llama3.1
ollama pull nomic-embed-text

# (optional) seed semantic memory from the existing EmberHeart corpus
python -m backend.ingest.ingest

# run
python -m backend.main          # -> http://localhost:8000
```

In the UI: open the **GM** tab → *Bootstrap start* and *Create* a hero → hit
**▶ Start session** → type what you do.

Run the offline tests (no Ollama needed):

```bash
pytest -q
```

---

## What it does

- **Live DM loop** over WebSocket: streamed narration, then a parsed result with
  applied mechanics, dice, and three player suggestions.
- **Three-layer memory** — working (this scene), semantic RAG (everything learned),
  structured state (the ground truth the LLM may read but never writes).
- **Deterministic mechanics** — the LLM *declares* changes via `[MECHANICS]` tags; the
  engine *enforces* them and owns every die roll.
- **Living world** — an in-world calendar with events that fire on their due date, a
  faction tick, kingdom decision events, and an optional always-on economy.
- **Combat** — initiative, zones, enemy-AI profiles (berserker / tactical / cowardly /
  spellcaster), and death saves, all resolved in Python.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/DECISIONS.md](docs/DECISIONS.md) for assumptions worth reviewing.

---

## Deploy to funiserver

```bash
./scripts/deploy.sh           # rsync + docker compose up --build
```

The container talks to the host's Ollama via `host.docker.internal`. Your campaign DB
lives in `./data` on the server and is **never** clobbered by a deploy.

---

## Configuration

All via `.env` (see `.env.example`). Highlights:

| Var | Meaning |
|-----|---------|
| `OLLAMA_BASE_URL` | OpenAI-compatible endpoint (`…/v1`) |
| `NARRATION_MODEL` / `ADJUDICATION_MODEL` | hot prose vs cold adjudication |
| `EMBED_MODEL` | fixed embedding model — **never change once populated** |
| `RAG_TOP_K` / `RAG_RELEVANCE_THRESHOLD` | retrieval depth + noise floor |
| `ECONOMY_TICK_ENABLED` / `ECONOMY_TICK_SECONDS` | the optional kingdom economy loop |
| `APP_PASSWORD` | optional shared-password gate over `/api/*` |

---

## API surface (selected)

| Method | Path | Purpose |
|--------|------|---------|
| WS | `/api/play/ws` | streamed DM turn |
| POST | `/api/play/action` | buffered DM turn |
| POST | `/api/session/start` | faction tick + "Previously on" recap |
| GET | `/api/world` | world + factions + quests + domain + chronicle |
| POST | `/api/world/advance` | advance the calendar |
| POST | `/api/world/found-domain` | enter the kingdom phase |
| POST | `/api/combat/start` · `/advance` · `/end` | run combat |
| POST | `/api/memory/search` | probe semantic memory |
| GET | `/api/health` | Ollama reachability + model list |
