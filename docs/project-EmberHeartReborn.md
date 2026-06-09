---
name: project-emberheartreborn
description: Working memory for the EmberHeartReborn project — a local-Ollama AI Dungeon Master for a fresh-reboot EmberHeart campaign
metadata: 
  node_type: memory
  type: project
  originSessionId: f5b6fe39-6385-4a4b-b30d-da3c4a168ca5
---

## State / goals
`/Users/todd/Projects/EmberHeartReborn` — a specialized **AI Dungeon Master** ("Chronicle
Weaver") for a long-running EmberHeart campaign. Built greenfield this session from a full
spec doc the user wrote (`/Users/todd/Projects/# Emberheart AI Dungeon Master — Full Sy.md`).
Stack: FastAPI + SQLite (raw `sqlite3`, no ORM) + no-build Preact/htm UI; local Ollama via the
OpenAI-compatible `/v1` endpoint. Three-layer RAG memory, deterministic homebrew mechanics, a
living world that runs an **origins → kingdom-building** arc.

Status: a **trustworthy beta** the user is actively *playing*. Campaign can't be lost
(undo/backups), DM contract adherence proven, model-agnostic (local + Ollama cloud), mobile
UI + installable PWA. Live server runs on `:8000`; run pattern:
`nohup ./.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 ... >/tmp/eh-server.log 2>&1 &`.
**156 tests pass**; SCHEMA_VERSION=8; `.venv` is **Python 3.12** (not the 3.14 system default).
**NOW DEPLOYED & LIVE on funiserver:8000 — the canonical save lives there, not the Mac** (see Decisions/Sessions).
**Source is in a PRIVATE GitHub repo: `todell725/EHR`** (gh CLI logged in as todell725; `.env` + `data/` gitignored).
Frontend is static (refresh browser to pick up changes; hard-refresh to bust cache). Server reads
the DB live. Currently running on **`deepseek-v4-pro:cloud` + `FULL_CONTEXT=true`** (premium tier).
Tabs now: World, Heroes, Party, **Inventory**, Combat, Idle, Factions, Quests, **Journal**,
Kingdom, Memory, GM. User is playing on an **iPhone PWA**.

**CAMPAIGN STATE (2026-06-04) — THE ARC IS COMPLETE.** Kaelrath has **ASCENDED**: all four
domains (Dream, Memory, Fire, Sacrifice) claimed; reborn on the EmberHeart as the **God-Ascendant
Flamekeeper** — divine *and still himself* ("a hearth, not a sun"), the Creed kept, void-cold
burned away, max HP 35→55, L5 (L6 available). Married to **Talmarr** (queen/regent). Rides
**Cindermane** (fabled white stallion mount, bond maxed). Founded **The Kingdom of EmberHeart**
(now in **kingdom phase**, economy live; pop ~440, morale 5). Council: **Warden Renn, Hearthkeeper
Orina, Forgemaster Bheric, Loremaster Sella**. ~446+ chronicle beats; campaign validated rock-solid
across the whole ascension. Fire anchor = **Sol-Thairn** (last ember of the First Flame, now in the
vault). The whole back half was driven by **owner-authored cinematic beats** I wrote + applied +
pushed to the feed (see inject system below), not live model turns.
**CAMPAIGN STATE (2026-06-05) — POST-ASCENSION KINGDOM PLAY, deep in it.** EmberHeart is a thriving
**city of ~12,000** (population growth now hard-capped there by the user — logistics — via
`domain.housing_cap`). New live arc: the **EMPTY THRONE** — a faceless void-herald named **Kryoss**
stands at the north treeline (the void/"Singing Death" is back as the main threat). **Vaelis Thorne**
(tiefling arcanist, one of the old-party "wives") just **arrived** bursting into the council with the
only intel on the Empty Throne — now a tracked NPC (`NPC-vaelis`), slow-burn consort + the realm's
void-scholar; SEEDED SECRET the DM can spring: *Kaelrath's void-scar is a RECEIVER the Empty Throne can
reach through*. Active threads: the **ember-glass panoply/sword** (vision in his journal — to forge from
the Elder Ember-glass Heart + 31 shards + obsidian steel + dragon's gold + sun stone, at the Shardwork
with Bheric + Sol-Thairn); consort hooks for **Silvara** (bard) & **Mareth** (knight) still pending
(not yet arrived). EmberHeart now has an AI-art **visual codex** in the Gallery tab (canon images).
**CAMPAIGN STATE (2026-06-08) — DAY 82, THE EVE OF THE CORONATION (user is about to PLAY the crowning).**
Since the Empty-Throne reveal: Kaelrath grew **ASCENDANT WINGS** (ember-glass-and-fire dragon wings —
real flight, "a hearth not a sun"; the louder light-speed **Flamewalk** is the riskier alt that beacons the
void) and we codified that divine acts run on a **3-tier cost curve** (domain-aligned = free; reality-bending
= costly; against-nature = Sacrifice). He spent **72h at the God-Forge** making divine-steel GIFTS for the
council (Renn's void-cold sword, Bheric's hammer, Sella's stylus, Vaelis's void-proof resonator-fork, Orina's
tools, Talmarr's arrows + himself; district hearth-relays). Then a **3-week montage**: flew out and claimed
**obsidian steel** (Fire-domain guardian, by being *known* not fighting) + **dragon's gold** (a dead dragon's
cairn); the **Shardwrought Panoply is FORGED but for one empty socket** — the **sun stone** sits in the
**Sunken Caldera, a Sundering-wound that knows his void-scar by name** (Vaelis flagged it; DEFERRED until
after the coronation = the next great quest, ties to the Empty Throne). Kingdom: pop ~12k, **7 standing crews
seeded** in the Labor tab (Ranger Drills, King's Relay, Void-Watch, N. Trade Caravan, Hearth-Channel Sweep=32
one-per-ring, Smiths' Crew, Housing Crew) + 3 buildings (Barracks, Tool-Works, Void-Ward Sanctum).
Architectural ancestors / corpus: [[project-dnd]] (Claudes-EmberHeart rich corpus),
[[project-emberheart-origins]] (FastAPI+Ollama ancestor), [[project-emberheart-citybuilder]].

**The player's character is Kaelrath Emberhide** — Dragonborn (Fire), Rogue/Soulknife, "former
smith's apprentice" (card from `Claudes-EmberHeart/docs/PARTY_STATE.json` PC-01). The
`emberheart-origins` Kaelrath profile is the FUTURE god-king (Custom Divine; fire/memory/
sacrifice/dream) = foreshadow, NOT the playable card. Played at origins-era level 1.

**Live campaign narrative (don't contradict):** Origins era. PC-01 began as placeholder human
"Ash Vorn", then was transformed **in-story** into Kaelrath (Dragonborn) at the cipher-resonance
beat — the "Ash" chronicle beats were deliberately KEPT as his human past (the reveal: Ash *was*
Kaelrath, dragon-blood dormant until the buried cipher woke it). Arc so far: dark frontier camp →
spiral of warm geomantic stones → sealed artificial wall → bone-fragment cipher (reacts to
intense focus; emerald flare) → Kaelrath's awakening. **Talmarr (she/her), ally/scout**, warned
of a "forgetting void" in the north. ~20 open hooks; central mystery = a buried sealed vault /
the forgetting void.

## Decisions
- **Canon = FRESH REBOOT.** The Dnd/Claudes-EmberHeart + emberheart-origins corpus is ingested
  as **seed lore/foreshadowing only, NOT authoritative state.** Golden-Age / post-scarcity /
  god-king material is auto-tagged `era='future_foreshadow'` (keyword classifier in
  `ingest/ingest.py`) and excluded from normal retrieval. Campaign deliberately starts dark/
  small (origins) and grows into ruling a domain.
- **LLM = local Ollama only** — free, self-owned, no content policy (suits the mature/romance
  threads). Matches [[feedback-prefer-lightweight-tooling]].
- **Ruleset = existing homebrew, NOT 5e SRD.** 5e-derived core (ability scores, AC/HP, d20,
  proficiency) + RuneScape-style idle-skill XP ladder. Codified in `backend/rules/homebrew.py`
  with documented assumptions A1–A5. **Character level-up is GM-confirmed** (corpus XP curve
  diverges from 5e: 522k XP @ L20).
- **World cadence = phased hybrid.** Session/calendar-driven core always on; the always-on
  resource economy is built but **toggled OFF until a domain is ruled** (`found_domain` flips
  `arc_phase` to kingdom + wakes the economy tick). **Kingdom now FOUNDED** (The Kingdom of
  EmberHeart), economy live.
- **INJECT system — push hand-authored DM beats to the live feed** (`broker.inject()` +
  `POST /api/play/inject`, display-only — does NOT run the model or apply mechanics). This is how
  the whole back-half (montages, the ascension, scenes) got delivered: I write a beat's narrative +
  applied-chips + suggestions, **separately apply the real state via direct DB writes**, then inject
  the prose so it appears as a Chronicle Weaver turn. Inject uses a **timestamp-based seq** so it
  always renders past a stale client. **Replay buffer:** `broker.recent` (deque maxlen 12) +
  WS-connect replays the whole buffer (deduped client-side by seq) — fixes that injecting twice used
  to overwrite the first beat so the user never saw it. Workflow each beat: (1) python script does
  `state.*` writes (XP/drops/scene/chronicle/journal/etc.), (2) python script POSTs the narrative to
  `/api/play/inject`. After a montage/scene I **revert any verification test-writes** I made.
- **The ASCENSION arc (designed + fully played this session).** EmberHeart = forge/anchor of rebirth;
  four domain-crystals (🌙Dream 🕯Memory 🔥Fire ⚖Sacrifice) gathered, then **mortality offered on the
  pyre → reborn**. Tracker (`meta.ascension`, `/api/ascension`, Heroes-tab UI; statuses
  unknown→revealed→in_progress→claimed). DM-facing **`arc_note`** in `meta` injected every turn by
  `working._arc_note()` (reveal-gradually + secrecy that relaxes as things are earned). The Creed —
  *"a living god among men, not a remade stranger"* — became the true climax (can he be burned down
  and rise still himself); the five anchors (teardrop/moon-charm/wall/strand/kingdom) + Talmarr's Vow
  are what hold his humanity. **Three-syllable-name omen** ("Flamekeeper") paid off — he claimed it.
- **The Journal** (migration v7 `journal` table; Journal tab; `JOURNAL: <mood>, <reflection>` DM
  mechanic, sparingly) — reflective "feels", NOT quests.
- **Mount system** (migration v8 `mounts` table; `/api/mounts`; 🐎 card on Heroes tab; `MOUNT_TAME`
  mechanic + aliases; DM sees `MOUNTS:` in working memory). Cindermane = Kaelrath's fabled white
  stallion (fire-fearless — the mount that carries the Flamekeeper into fire).
- **Idle↔world bridge (materials).** Idle skill XP already fed the sheet; now **materials** do too:
  DM sees `CAMP STORES:` in working memory and can spend/award via `MATERIAL_SPEND`/`MATERIAL_GAIN`
  (+aliases); player can **deposit idle stores → pack** (`/api/idle/deposit`) or **→ kingdom
  stockpiles** (`/api/world/invest`, mapped wood→lumber, raw_meat/berries/fish→food, ore→ore). Keys
  normalized via `state.normalize_material` (logs→wood, meat→raw_meat, …).
- **Inventory tab** (own tab, drop/adjust qty, 🧹 Tidy = merge dupes + strip junk;
  `/api/pcs/{id}/inventory/set|tidy`). Moved off the cramped Heroes sheet.
- **KINGDOM MANAGEMENT DASHBOARD — built collaboratively with a second agent ("kimi").** Org model
  the user runs: **kimi = junior dev (builds), me = senior dev (reviews/hardens), user = PM/QA**.
  Lane discipline: kimi owns `sim/kingdom.py` (buildings/projects/labor), `sim/economy.py` depth,
  `api/world.py` kingdom endpoints, and `KingdomPane` in `app.js`; I own DM-side mechanics
  (`mechanics.py`, `prompt.py`), the economy starvation fix, and review. Shared contract: the domain
  ledger stays in **`meta.domain`** (JSON) behind `kingdom.get_domain()/set_domain()` — keep those
  + field names (`morale/treasury/military/population/infrastructure/stockpiles`) stable or both
  sides desync. **`KINGDOM_CHANGE` DM mechanic** (mine): the DM moves the realm from the story
  (`KINGDOM_CHANGE: morale, +1` / `treasury, -200` / `food, +500`) — stat synonyms + tag aliases;
  morale clamps 1–5. **Building system** (kimi): full ~37-building catalog by category w/ `requires`
  prereqs, `cost`, `turns`, one-shot `effect` (applied on completion) + **`ongoing` dict read live by
  `economy.py`** (granary food_cap_mult, workshop/shardwork craft_bonus, market/hearth_hall
  trade_income, quarry_ore, aquaculture_food, brewery_morale, pop_cap_bonus, mender_soften…). 3
  pre-built (blood_wall/ember_vault/god_forge) seeded on founding; `memorial_wall` auto-builds at 10+
  chronicle beats. Catalog spec lives in `docs/kingdom-building-prompt.md`. **Smart `auto_labor()`**
  (mine, `/api/world/labor-auto` + ⚡ button): priority bands — famine→58% farming, tight→46%,
  building→32% craft, prosperous→balanced+defense — never an even split, always sums to pop, returns
  a rationale string.
- **Post-ascension = KINGDOM-BUILDING MODE.** When `domain_ruled`, `working.py` injects a KINGDOM
  ledger line + a directive to **slide from questing to rulership**, with the user's **ruler's-day
  rhythm** (wake → council → tackle the day's problems) and a strict **COUNCIL MEETING FORMAT**: (1)
  State of the Realm stats, (2) each advisor reports on their domain + brings one proposal
  (Warden Renn=defense, Hearthkeeper Orina=food/people, Forgemaster Bheric=building/industry,
  Loremaster Sella=lore/threats, Queen Talmarr=co-ruler) + noble proposals/petitions/upgrades, (3)
  council reacts/debates, (4) **stop for Kaelrath's final ruling** (don't decide for him). **Build
  ticks now advance one per play-beat** (orchestrator calls `kingdom.tick_projects()` per turn when
  `domain_ruled`) so construction keeps pace with the story; the manual "Tick projects" button still
  works. **Private companion chat now uses the DM's model** (`companion_chat.send` calls
  `routing.pick_narration_model` → deepseek + same intimate routing as the game, not the cheap
  `chat_model`).
- **Gallery** (`frontend/gallery/` folder + `GET /api/gallery` + Gallery tab w/ lightbox): drop-a-file
  visual codex, zero-DB. The folder IS the gallery — images served static at `/gallery/<file>`, the
  endpoint enumerates them, optional `gallery/captions.json` maps filename→caption (else prettified
  filename). Used for AI-generated **canon art** of EmberHeart (aerial city, gate, Kaelrath portrait,
  Kaelrath-vs-Kryoss, the vault, the ember-glass panoply). Image-prompt style that works: comma-
  separated visual nouns, "warm amber city vs cold blue-white snow" contrast, lava-veined black wall,
  district-wheels each with a hearth-fire.
- **`KINGDOM_CHANGE` is mine; the council "approve via SUGGESTIONS multi-select" is a UI thing** — the
  play-feed suggestions are now **toggle-select + a "▶ Do these (N)" button** (pick several, sent as
  one combined action "I'll do these: …") instead of click-to-send-immediately. Good for greenlighting
  multiple council proposals in one turn.
- **`auto_labor()`** (`/api/world/labor-auto`, ⚡ button): smart priority-band labor split (famine→58%
  farming, tight→46%, building→32% craft, prosperous→balanced+defense) — never even, always sums to
  pop, returns a rationale.
- **Old-corpus reuse for NPCs/wives:** the user's past-game "wives" = the old PC party women in
  `Dnd/Claudes-EmberHeart/docs/PARTY_STATE.json` (PC-02 **Talmarr** = current queen; PC-03 **Silvara**
  bard, PC-04 **Mareth** knight, PC-05 **Vaelis Thorne** tiefling wizard). Romance styles in
  `NPC_ORIENTATIONS.json`. The **CONSORT FRAME** is seeded as a hook: EmberHeart tradition lets the
  Flamekeeper take more than one wife; Talmarr stays queen-first and content; new bonds are SLOW/earned,
  never framed as cheating on Talmarr.
- **Dynamic building catalog:** the static `BUILDINGS` dict is merged with story-proposed buildings
  via `kingdom.all_buildings()` (custom ones in `meta.custom_buildings`); ALL consumers route through it
  (get_summary catalog, start_building, tick_projects, economy `_ongoing`). The DM/council proposes one
  with **`BUILDING_PROPOSE: <name>, <category?>`** → instantly buildable in the Kingdom tab. `add_building()`
  is the helper.
- **Building upgrades:** a catalog entry with `upgrades_from: <base_key>` is an upgrade — completing it
  REPLACES the base in `built` (tick_projects). UI hides upgrade entries from the normal list and surfaces
  them as an **"⬆ Upgrade"** button on the built base.
- **Crews/Teams** (`domain.crews` = [{name,size,role}]): editable in the **Labor sub-tab** (add/resize/
  remove → `POST /api/world/crews` → `set_crews`); the council stands one up in-story via **`CREW_SET:
  <name>, <size?>, <role?>`** (`add_crew`). **Crews are injected into DM working memory** ("honor these
  numbers, react to changes") so the council SEES the ruler's allocations. 7 crews seeded from play.
- **Memory = SQLite + numpy brute-force cosine** (corpus <10k chunks → no vector server/Chroma).
  Embeddings via `nomic-embed-text` (768-dim). **Never change the embed model once populated** —
  mixing breaks cosine; the `dims` column is the tripwire.
- **Output contract:** four sections `[NARRATIVE]/[MECHANICS]/[SUGGESTIONS]/[CHRONICLE]`. LLM
  *declares* changes via tags; deterministic Python *applies* them; **Python owns all dice.**
  `STRICT_OUTPUT=true` switches to a guaranteed-parseable JSON contract (escape hatch for model
  drift) at the cost of live streaming.
- **DEPLOYED & LIVE on funiserver (2026-06-08).** Container `emberheart-reborn` on **funiserver:8000**
  (tailnet `100.114.116.111`), build dir `/mnt/user/appdata/emberheart-reborn`, **canonical save at
  `…/data/emberheart.db`** (the Mac copy is now just a backup — DON'T play on the Mac, it'd diverge).
  funiserver runs Ollama (container **`ollama`** = official `ollama/ollama` :11434 — see the OllamaUI
  saga in Gotchas) on an **RTX 3060** with all needed models: `deepseek-v4-pro:cloud` (narration),
  `gemma4:e4b` (adjudication/chat/fallback), `nomic-embed-text` 768-dim (memory), and intimate
  **`dolphin3:8b`** (Llama 3.1 8B uncensored — replaced the `sparksammy/samantha…20b` that wouldn't pull).
  Models live on the host volume **`/mnt/user/Data/LLM`** (survive container swaps). App reaches Ollama via
  `host.docker.internal:11434/v1`. The old `emberheart:origins` container was RETIRED to free :8000. **`scripts/deploy.sh`** = one-command push
  (runs pytest → rsync code → `compose up -d --build` → health-check); it PROTECTS `data/`, `.env`, and
  `frontend/gallery/*` images (gallery images now live server-side; `captions.json` still syncs). I can
  SSH to funiserver (root). `.env` not in git.
- **No-cache middleware (`revalidate_static` in main.py):** HTML/JS/CSS now return `Cache-Control:
  no-cache` + ETag so UI changes show up without the old hard-refresh / iOS-PWA-swipe-kill fight (cheap
  304s). **Mobile fit fixed:** `viewport-fit=cover` + black-translucent status bar needed `env(safe-area-
  inset-*)` insets on header/composer/drawer (content was under the Dynamic Island / home indicator);
  plus `overflow-x:hidden` + `min-width:0` guards and a mobile stack for the crews grid. Also the play
  feed's **suggestions now auto-fold** on mobile when you scroll up to read (log `onScroll` → `collapsed`
  class → max-height transition; desktop unaffected; they return at the bottom / on a new beat).
- **The feed is now DB-BACKED (`broker.recent` persists).** Injected/montage beats were IN-MEMORY only
  (`broker.recent`, deque maxlen 12) → wiped by every container restart/deploy (the live game STATE always
  survived; only the *display* of injects was lost). Fix: `_persist_feed()` writes the buffer to
  `meta.feed_recent` on every turn/inject; `broker.restore_feed()` reloads it in the lifespan startup
  (after `db.init_db()`). So the last 12 beats now survive refresh, app-close, AND restart. **Gotcha when
  re-pushing a lost inject: re-inject AFTER the deploy that added persistence** (an inject through the old
  code won't be on disk, so the deploy's restart wipes it again).
- **Source in PRIVATE GitHub `todell725/EHR`** (gh CLI authed as todell725, HTTPS). `git push` to ship.
  `.gitignore` excludes `.env`, the WHOLE `/data/` dir (DB + backups/ + snapshots/ — first attempt only
  ignored `/data/*.db` and missed the subdirs, nearly committing ~150 backup DBs), `/logs/`, and gallery
  image binaries (captions.json + README kept). `.env.example` IS tracked as the config template.
- **Trust-boundary hardening (from code reviews, 2026-06-08/09):** added `test_mechanics_adversarial.py`
  (25 hostile/malformed tags → never crash, never corrupt; HP clamps, no neg stacks, injection-safe). The
  boundary noted unknown tags but a malformed KNOWN tag fell to `applied` as "(unhandled)" → routed to
  `notes`. **Inject can now carry validated mechanics** (`InjectBeat.mechanics` → `apply_inject_mechanics`
  → through `apply_mechanics`) so authored beats can't split-brain prose vs state — dogfooded paying the
  16-quest back-bounty. **Narration resilience:** first-token fallback already covered a slow START; added
  **mid-stream drop recovery** (cloud "incomplete chunked read") — `_narrate` catches it, emits a
  `("reset")`→`{"type":"narrative_reset"}` that WIPES the partial on-screen text, regenerates on the
  fallback model (also fixed the refusal double-narration the same way). **Faction resources clamped**
  `[0,40]` + mean-reversion (were unbounded-up → runaway dominance; rep was already ±100). **Idle skill
  levels already auto-apply** (no GM queue) — surfaced them (chronicle beat) so they're not silent.
  **`CONDITION_ADD` dedups** (re-apply refreshes duration) + comma-safe name parse. **`scripts/reembed.py`**
  re-embeds the whole corpus with a new EMBED_MODEL (removes the one-way-door). **RAG cosine** now runs via
  `asyncio.to_thread` (off the event loop). PUSHED BACK on the reviewers re: raw-SQLite-ORM (single-writer,
  fine), Alembic (version-gated migrations + narrow dup-column net is enough), and "dynamic SQL f-strings"
  (identifiers are code-literal column names, values parameterized → injection unreachable by construction).
- **Quest cards have a "↪ Pick this up" button** → `POST /api/play/submit` (new — enqueues a turn through
  the BROKER so it STREAMS to the feed, unlike `/play/action` which runs detached) → DM re-engages the
  thread live. Closes the sidebar on success.
- **Model tiers (engine is model-agnostic — just change `NARRATION_MODEL`):** (1) FAST LOCAL
  `gemma4:e4b` (default, ~3–20s); (2) PREMIUM cloud `deepseek-v4-pro:cloud` (~26s warm, fastest
  cloud, 0 rejected) + `FULL_CONTEXT=true`; also `glm-5.1:cloud` (~33s), `kimi-k2.6:cloud` (~60s
  warm / 156s cold, most literary). All cloud models hit **0 rejected** with the hardened
  contract. Cloud breaks the "local-only/self-owned" principle — conscious tradeoff for quality.
- **`FULL_CONTEXT` mode** (`working.build_full_context`): inject the WHOLE campaign (full
  chronicle + all hooks/NPCs/factions) instead of RAG top-k — only for big-window models; makes
  drift structurally impossible.
- **Content routing "if romance then samantha-20b"** (`backend/dm/routing.py`): `ROUTE_INTIMATE`
  + `INTIMATE_MODEL=sparksammy/samantha-uncensored-v5:gpt-oss-20b`. Proactive keyword detection
  + reactive refusal-fallback (regenerate on the uncensored model if the primary refuses).
- **Latency fallback layers:** `NARRATION_TIMEOUT` (75s steady, kimi-aware), `COLD_START_TIMEOUT`
  (180s grace for a model's first/cold call → drops to steady once warmed), `FALLBACK_MODEL`
  (→ gemma if primary stalls/errors). Models warmed on page-load `/api/warmup` + session start.
- **Picked deepseek over kimi for premium.** kimi (~60s) kept tripping the 75s budget → constant
  fallback to gemma ("kimi dropped a lot"). deepseek-v4-pro (~26s) has headroom. ADJUDICATION
  stays local gemma (cheap repair/consolidation/summaries — don't pay cloud for those).
- **DM was too lethal** ("actively trying to kill me"). Softened the prompt: be a FAN of the hero
  (not executioner), TELEGRAPH deadly threats + leave an out, SCALE danger to level, vary texture
  (not every beat is a fight/trap/save). Grounded-dark ≠ cruel.
- **Party companions** (`is_player=0` rows in `player_characters`): reuse the whole sheet/level-up/
  combat machinery, but DM-controlled. Recruit via `PARTY_JOIN: <name>` tag (in-story) or the
  Party-tab button (`POST /api/npcs/{id}/promote`). Class inferred from role. Heroes tab =
  `is_player=1`; Party tab = `is_player=0`. In combat, companions are party-side **DM-run allies**
  with a simple ally AI (attack weakest enemy, 1d8+mod); heroes hand control to the player.
  `state.heroes()`/`companions()` split; `list_pcs()` returns both (combat/XP want both).
- **Character sheet + level-up engine** (`backend/rules/progression.py`, migration v4 `features`
  column): Rogue+Soulknife tables encoded; ASI/feat/expertise choices + custom homebrew action/
  spell add; generic fallback for other classes (HP+prof only). Sheet API `/api/pcs/{id}/sheet`,
  `/levelup` (GET preview / POST apply), `/seed-features`. PC features are injected into DM working
  memory (the fix for "the LLM didn't get the meta-level"). Level-up is XP-gated with GM override.
- **Unknown DM tags** are no longer rejected: `mechanics._ALIASES` maps ~70 invented synonyms onto
  real tags (DAMAGE→HP_CHANGE with sign flip, LOOT→ITEM_ADD, RECRUIT→PARTY_JOIN, …); anything still
  unrecognized is **soft-noted** (`notes`, shown as ✎) instead of ⨯-rejected. Prompt also tells the
  DM not to invent tags. `rejected` is now only malformed *known* tags.

- **Ascension arc (Kaelrath: god-touched → God-Ascendant "Flamekeeper").** Designed with the user.
  Structure: the **EmberHeart is the central anchor / forge of rebirth**; **four domain-crystals**
  (🌙 Dream, 🔥 Fire, 🕯 Memory, ⚖ Sacrifice) lie across the ley-network as weary guardians to
  **relieve** (take their burden). The **ley-anchor = Dream (in progress)**; its **sister anchor**
  (current quest, north-northwest) = a 2nd domain, **Memory or Sacrifice — TBD, to be revealed when
  he pulls it in play**. Climax/price: **sacrifice his mortality on the EmberHeart → reborn**
  (echoes Ash→Kaelrath). Implemented: (1) a DM-facing **`arc_note`** in `meta` injected every turn
  by `working._arc_note()` into the scene block — tells the Weaver the whole path but says **reveal
  GRADUALLY + SECRECY: the title "Flamekeeper"/"god-touched"/domain names are PLANNING-ONLY, no NPC
  may speak them until earned**; (2) **Ascension Tracker** UI on the Heroes sheet (`/api/ascension`
  GET + `/domain` POST; state in `meta.ascension`; EmberHeart center + 4 crystals, status
  unknown→in_progress→claimed). **Emergent foreshadowing the user loves:** the same **three-syllable
  echo** surfaced twice unbidden (void-stalker's death-echo from the shimmer; Talmarr's unexplained
  slip calling him "Flamekeeper") — logged as **omen chronicle beats** (the world whispering his true
  name pre-reveal); keep it as mystery, never state it as known.
- **The Journal** (migration v7 `journal` table; `/api/journal` GET/POST/DELETE; Journal tab) — a
  place for reflective "feels" (mood/title/body), NOT quests. DM can auto-write entries via a
  **`JOURNAL: <mood>, <reflection>`** mechanic (first-person, hero's voice; prompt says use SPARINGLY
  on big emotional beats only). Moved 3 emotional-theme "quests" (consolidation artifacts) here.
- **Quest hygiene:** Quests pane now has **Active/Completed sub-tabs**. Reconciled the log: marked 7
  genuinely-done quests complete (moonveil, Barrow/Talmarr's-fate, Forge of Redemption, EmberHeart's
  Awakening, both vault-prep dupes, EmberHeart Focus), **merged 5 duplicate "sister anchor" quests**
  into one canonical active *Seal the Northern Wound (the Sister Anchor)*, and **granted milestone
  back-pay**: Kaelrath +2000 XP (4750→6750, **now L5, level-up available**), Talmarr +1200 (→4150,
  still L4). `meta` table lives in `schema.sql` (not a migration); journal helpers in `state.py`.

## Gotchas
- **THE OLLAMA "Connection error" SAGA (2026-06-09) — root cause was infra, not the app.** The old Ollama
  container was **`OllamaUI`** (`ghcr.io/chrizzo84/ollamaui:main`, a bundled Ollama-server + WebUI image).
  Its Docker **healthcheck pinged the WebUI on :3000, which was dead** → container marked `unhealthy` →
  the **`autoheal`** container (`AUTOHEAL_CONTAINER_LABEL=all`, watches everything) **killed+restarted it
  every ~2.5 min** → the Ollama server (:11434) the game depends on kept dropping → turns landing in a
  restart window got "LLM unavailable: Connection error" (deepseek AND the gemma fallback both fail because
  Ollama itself is down). Diagnosis trail: `docker events` showed `health_status: unhealthy → kill(15) →
  die(143) → restart` on a clock. **Fix:** the user replaced it with the plain **official `ollama/ollama`**
  image (no WebUI, **no healthcheck → autoheal-safe**); models persisted via the `/mnt/user/Data/LLM`
  volume mount. (Alt fix if it recurs: label the container `autoheal=false`, or point its healthcheck at
  `:11434/api/version`.) **Lesson: a flapping `autoheal` + a bundled image's broken WebUI healthcheck can
  silently nuke a dependency.**
- **Ollama pulls choke on multi-stream over this network.** Any model >~3-4 GB stalls mid-download
  (`OLLAMA_MAX_TRANSFER_STREAMS:4`, silent stall, no error) — samantha-20b died at 4.2 GB, dolphin3 at
  3.1 GB. **Fix that works: single-stream.** Cleanest without touching the main container: run a throwaway
  `docker run -e OLLAMA_MAX_TRANSFER_STREAMS=1 -v /mnt/user/Data/LLM:/root/.ollama ollama/ollama`, exec
  `ollama pull` inside it (FOREGROUND — `docker exec -d`/nohup die because the image has no init to adopt
  orphans), then `rm` it; the model lands in the shared volume. Resumes from the partial.
- **`QUEST_COMPLETE` was a silent no-op (fixed 2026-06-09).** It was aliased to `QUEST_UPDATE`, which only
  flipped status when `args[1]=="completed"` — but `QUEST_COMPLETE: <title>` has no `args[1]`. So the DM
  never actually closed quests (16 piled up unclosed, no rewards). Now it's a first-class tag + fuzzy
  title match (`_find_quest`) + the prompt tells the DM to close+reward. Quest rewards only fire if a quest
  is CLOSED, so this also explains the "where's my loot?" gap.
- **Dead-key class of bug keeps recurring — always grep that an `ongoing` building key is actually
  read in `economy.py`.** Fixed twice now: kimi's first buildings (granary/workshop/market) and again
  **"supplies"** (the stockpile was NEVER produced by the tick — Weaver's Guild/Tannery/Alchemist's Den
  claimed a supplies bonus but it was dead). Now supplies comes from craft labour + `supplies_out` on
  those 3 buildings.
- **Population growth `pop_cap` was a per-tick THROTTLE, not a ceiling (fixed).** Old code did
  `pop_cap = pop + pop_cap_bonus` recomputed each tick → capped growth to ~20/tick forever instead of
  letting it run to a real housing limit. Fixed: growth runs at natural `pop//65` (~1.5%/tick) up to
  `domain.get("housing_cap")` (a real ceiling). Set `housing_cap` to expand/cap population;
  ring_housing `pop_cap_bonus` bumped 20→288 (= 36 cabins × 8 souls, honest per-district). The user
  HARD-CAPPED pop at ~12k for now (set housing_cap = current pop). Refugees can still be added in-story
  via `KINGDOM_CHANGE: population, +N`.
- **iOS-PWA / desktop frontend cache:** `index.html` loads `/app.js` with NO cache-bust, so EVERY UI
  change needs a hard-refresh (desktop ⌘⇧R) or PWA swipe-kill-reopen. Offered a `Cache-Control:
  no-cache` middleware — still pending if the user wants it.
- **Idle-materials RACE / dupe (fixed).** `idle.tick()` read the whole `idle_materials` blob, worked,
  then wrote it back — so a concurrent deposit/invest/`MATERIAL_SPEND` (or the background `_idle_loop`
  on another thread) got **clobbered by a stale snapshot**, "restoring" spent materials (the user's
  larder inflated; deposits never depleted). Fixed: all material read-modify-writes serialize on
  `state.MATERIAL_LOCK` (RLock); `tick()` does its gate+spend inside it with a fresh read.
- **Inventory `ITEM_REMOVE` never depleted (fixed).** Old handler removed only on EXACT name match and
  ignored qty — so "give moonveil" vs a "Moonveil stalks" stack → no-op. Now: `_pc_and_item_args`
  (don't eat the item token as a PC name), `_match_inv_item` (fuzzy: exact→substring), decrement by
  qty, and `ITEM_ADD` merges into the existing stack (stops dup stacks like Moonveil×3 spellings).
- **Economy STARVATION flaw (fixed).** `economy.tick` grew population unboundedly but production was a
  **fixed founding labor count** (food_in ~constant) while consumption scaled with pop → any growing
  realm starved, morale floored at 1 (user hit it at pop 425). Rewrote so production scales with pop
  via labor **fractions**, added a self-healing morale floor of 2 ("a living hearth-god"), a `pop*0.05`
  "Flamekeeper's hearth-blessing" food trickle, gentle ~1.5%/tick growth, and a `pop*6` food soft-cap.
- **"tak" → "tack" hallucination (patch pattern).** DM misread a typo ("get the tak from bheric" =
  Cindermane's **tack**) and confabulated a whole "dome schematics" scene + bogus inventory item. Fix
  workflow the user liked: **patch in place** — strip the bogus item, set the right one, fix the scene
  + a corrected chronicle beat, and **inject a corrected DM beat**. (Alt offered: roll back via
  `/api/play/session/undo`.) When a turn looks wrong, read `meta.last_turn` (action + result narrative).
- **Inject overwrite (fixed via replay buffer)** — see Decisions; injecting two beats back-to-back used
  to leave only the last visible on reconnect.
- **Comma-split CONDITION/ITEM junk still leaks** into records (e.g. "Exhaustion"/"Minor Gas Strain" as
  inventory items, "Kaelrath, <item>" name prefixes). The Inventory 🧹 Tidy + manual curation clean it;
  root CONDITION_ADD hardening still deferred.
- **`db.upsert` rewritten to update-if-exists.** Partial upserts (`{id, hp}`) failed NOT NULL on
  existing rows because SQLite tries the INSERT branch first under `ON CONFLICT`. Now it does a
  real UPDATE when the row exists.
- **Combat integration bug (fixed):** `advance_to_player` stopped *at* the player's turn without
  consuming it, so enemy turns never resolved after the player acted. Split into
  `advance_to_player()` (opening, stop at player) vs `end_player_turn()` (consume the player's
  turn, then resolve enemies/death-saves). Orchestrator + `/api/combat/advance` use the latter.
- **Ollama models on this machine:** `gemma4:e4b`, `gemma4:31b-cloud`,
  `sparksammy/samantha-uncensored-v5:gpt-oss-20b`, plus cloud models. Did **not** have `llama3.1`
  or `nomic-embed-text` — pulled `nomic-embed-text`. `.env` set `NARRATION_MODEL=gemma4:e4b`
  (good prose in tests; the samantha-uncensored model is the option for explicit content if gemma
  soft-refuses).
- **Ingestion data shapes:** `NPC_STATE_FULL.json` is `{version, npcs:[...]}` (not a bare list);
  session logs live at `Dnd/session_logs` (one dir *up* from Claudes-EmberHeart). 354 chunks
  embedded after fixes.
- Seed a playable start before first run: `POST /api/world/bootstrap` + create a PC (the GM tab
  does both).
- **RECURRING BUG CLASS — comma-split mangles multi-word tag args.** The DM puts commas inside
  descriptions; the parser splits on commas, so `ITEM_ADD`/`WORLD_HOOK`/`CONDITION_ADD` got
  truncated or junk-filled (e.g. inventory `['5','3','Sample']`, hooks cut at first comma,
  conditions `['reinforced_eastern_wall','None','Exhaustion'×5]`). FIXED for items (rejoin +
  reject bare-number "items") and hooks (rejoin whole description). **`CONDITION_ADD` still
  vulnerable** — no rejoin, no dedupe, accepts non-conditions (cleared Kaelrath's manually). Open.
- **Numeric tag tolerance:** `_coerce_int` extracts the leading signed int from an arg, so
  `NPC_DISPOSITION_CHANGE: Talmarr, +5 (Trust/Urgency)` applies as +5 instead of being rejected.
- **Drift fix (the real one):** nothing re-grounded the DM once the recent-turns window scrolled
  off (~turn 20 amnesia). Added a persistent `scene` column (`SCENE_SET` tag, migration v2) +
  always-on "STORY SO FAR" block; **scene is auto-derived from the narrative's first sentence**
  each turn so it never depends on the model emitting `SCENE_SET`.
- **NPCs only existed in prose** — DM named characters but never `NPC_SPAWN`'d them, so
  disposition tags no-op'd. Fixed: `_ensure_npc` auto-registers a stub on any mechanical
  reference; dossier autofill (incl. pronouns) runs for spawned NPCs.
- **Pronouns:** `npcs.pronouns` column (migration v3); injected into NPC briefs + roster. Talmarr
  was misgendered "he" because there was no gender field — set to `she/her`.
- **Latency-fallback gotchas:** `await ait.aclose()` on an abandoned cloud stream BLOCKS ~30s
  draining the connection → use fire-and-forget `_abandon()` (background task). And an abandoned
  cloud request may keep generating server-side in Ollama (brief double-duty) — accepted tradeoff.
- **Snapshots/undo:** `data/snapshots/turn-NNNNNN-*.db` ring keyed by **global `turn_counter`**,
  15 deep; `data/backups/` for labeled. Restore = copy a snapshot over `emberheart.db` + `rm`
  the `-wal`/`-shm` files. Migration runner tolerates "duplicate column" so restoring an older
  snapshot then re-`init_db` re-applies migrations cleanly.
- **Hooks were write-only** until this session — now injected into the prompt ("OPEN THREADS"),
  resolvable (`HOOK_RESOLVE` tag), and clickable in the UI → `/api/hooks/{id}/dossier` does an
  LLM "what's known so far / uncertain / leads" synthesis (its LEADS section speculates beyond
  the notes — fine for brainstorming, don't treat as canon).
- **PWA icon:** source square PNG at `frontend/icon.png` (ember-heart, 1024²); `scripts/
  make-icons.sh` (macOS `sips`) generates apple-touch-icon/192/512/favicon. Re-run after swapping
  art. iOS caches home-screen icons — delete + re-add the shortcut to refresh.
- **STUCK-TURN / "acted twice, no response" bug (critical, fixed).** Turns had only a *first-token*
  timeout — a mid-stream cloud stall hung the broker on `status="running"` forever, so every new
  action was silently ignored ("a turn is already underway"). **Reopening the app does NOT fix it**
  (state is server-side). Fix: `TurnBroker.overall_timeout` (=max(300, cold_start+120)) wraps the
  stream consumption via `asyncio.wait_for`; `submit` supersedes a turn stuck past watchdog+30s. A
  server restart clears a live stuck turn.
- **`/api/play/state` crashed:** `last_persisted` is a module function in `broker.py`, was called as
  `broker.last_persisted()`. Now imported as a function. (Was breaking the REST recovery backstop.)
- **`NPC_SPAWN` didn't dedupe** → DM re-introducing a character created duplicates (had **3
  Talmarrs**). Fixed: NPC_SPAWN no-ops if the name already exists (`_ensure_npc` already deduped).
  Merged the live duplicates back to one Talmarr (she/her, Camp ally / scout).
- **iOS PWA refresh:** no refresh button in standalone mode — **swipe-close from the app switcher =
  hard refresh**. No service worker (intentional) so a full close/reopen pulls fresh code.

## Open / next
- **Main arc is DONE** — the user is now in **post-ascension free play** (a living god ruling the
  Kingdom of EmberHeart). Likely next threads: forging with the ember-glass haul (31 shards + an
  Elder Ember-glass Heart, for Bheric + Sol-Thairn — armor/weapon/relic/monument, user's choice);
  the northern wound / the Ley-Pact; winning the wider world; kingdom-building gameplay now that the
  economy is healthy. **Economy balance is fresh** — watch it over real play (it can run a big
  surplus + grow ~1.5%/tick; tune if it balloons again).
- **Harden `CONDITION_ADD`** (rejoin commas + dedupe + ignore non-conditions) — last instance of
  the comma-split bug class. User asked; deferred until after a play session.
- **Marathon drift** much improved by the scene/story-so-far grounding; >100 turns on a 4B model
  still unproven. Escape hatches: `STRICT_OUTPUT=true`, or switch to a big-window cloud model +
  `FULL_CONTEXT=true`. 20-turn local run was 100% narrative-ok.
- **LLM-driven combat** not watched through a full browser fight (all pieces unit-tested, the
  integration is wired). Eyeball the first real fight.
- **Economy/faction balance** is first-pass — needs the user's play *feel* to tune
  (`sim/economy.py`, `sim/factions.py`).
- **Companion combat AI is basic** (attack weakest enemy, 1d8+mod) — tune later. Non-rogue
  companions get no auto class features (only Rogue/Soulknife encoded in `progression.py`).
- **Kaelrath's L1 Expertise** (pick 2 skills) was skipped at character creation — offered to
  backfill, pending.
- **iPhone WS reconnect:** if reopening the PWA doesn't reconnect reliably, add a visible
  "reconnect" button (offered to the user).
- **TODO — extend companion chat to all NPCs** (not just party members). Needs (a) a new "Known
  NPCs" tab/roster, and (b) **availability/presence tracking** — can't 1-on-1 chat with an NPC who
  is in another location/"3 cities over" as if beside you. Gate chat partners by location/presence.
  (Companion 1-on-1 chat already built: gemma `CHAT_MODEL`, in-character, nudges disposition.)
- User was mid-action when the stuck-turn bug hit ("you sleep, I'll check the area" — checking the
  surroundings while Talmarr recovers); told to swipe-close + reopen + re-send.
- **UI** syntax-checks (`node --check`) and serves, but not browser-clicked by Claude — user's
  first session is its real test.
- Reliability check after any prompt/model change:
  `PYTHONPATH=. ./.venv/bin/python scripts/playthrough.py --turns 30`.
- Deferred (architecture leaves seams, not built): multiplayer PCs, TTS of narration,
  procedural map/image gen, Discord front-end.
- Plan file: `/Users/todd/.claude/plans/new-project-built-for-calm-pearl.md`.

## Sessions
- 2026-06-01 — Built the whole project from the user's spec (12 steps: config/LLM client →
  SQLite/DAL → homebrew+dice → 3-layer memory → ingestion → DM orchestrator/parser/router →
  sim (calendar/factions/kingdom) → combat → economy toggle → API/WS → Preact UI → Docker/deploy).
  Then a full hardening pass A–E: snapshot/undo safety net, mechanics linter + few-shot + repair
  + strict-JSON mode, combat integration (+ fixed the turn-resolution bug) + condition ticking +
  combat UI, WS reconnect/auth/tests + toasts, migrations runner, retrieval dedupe, NPC dossier
  auto-fill, session-end summaries, PLAYBOOK + pinned deps. Live 12-turn playthrough hit 100%
  narrative-ok / 0 exceptions / 0 invariant violations. Pulled `nomic-embed-text`. Server left
  running on :8000 against the live campaign DB.
- 2026-06-02 — Live-play session + feature work. Fixed two real play bugs from the user's screenshot:
  numeric-arg rejection (`_coerce_int`) and turn-20 drift (persistent `scene`/SCENE_SET + STORY SO
  FAR + auto-derived scene). Rolled the campaign back via snapshots to the bone-cipher beat. Fixed
  item/NPC tracking (comma rejoin, `_ensure_npc` auto-register). Made hooks a real mechanic
  (prompt injection, `HOOK_RESOLVE`, clickable dossier with LLM synthesis). Benchmarked Ollama
  cloud models (deepseek fastest); added content routing (samantha-20b for romance), `FULL_CONTEXT`
  mode, and the latency/cold-start fallback ladder. Added NPC pronouns (Talmarr → she/her).
  Made the UI mobile-friendly (drawer) + an installable PWA with the user's ember-heart icon. Set
  the player's PC to **Kaelrath** and staged his **human→Dragonborn awakening** at the cipher beat.
- 2026-06-02 (cont.) — Built the **character-sheet + level-up system** (progression engine, Heroes
  tab) and the **Party/companion system** (DM-controlled allies you level; combat + XP wired; Party
  tab + recruit). Fixed the **unknown-tags** flood (alias map + soft notes, not rejections) and
  **NPC_SPAWN duplicate** bug (3 Talmarrs → 1). Added a **live model display** in the header. Swapped
  premium model **kimi → deepseek** (kimi kept dropping) and **softened the DM** (was too lethal).
  Fixed a **critical stuck-turn bug** (no overall turn timeout → broker wedged on a mid-stream stall,
  silently ignoring further actions) with a 300s watchdog + supersede, and fixed the crashing
  `/api/play/state` endpoint. 66 tests pass.
- 2026-06-03 — Campaign **validated to ~313 turns** ("rock solid, only minor hallucinations that
  don't matter"). Designed + built the **ascension arc** (four domain-crystals anchored by the
  EmberHeart; price = mortality, reborn): DM-facing `arc_note` injection (reveal-gradually +
  secrecy), **Ascension Tracker** sheet UI, `/api/ascension`. Caught + sealed a **premature
  "Flamekeeper" leak** (the arc note's title bled into Talmarr's dialogue) and turned it + the
  void-stalker death-echo into a kept **three-syllable-name omen** thread. Built **the Journal**
  (migration v7, Journal tab, `JOURNAL` DM mechanic for auto "feels"). **Reconciled the quest log**
  (7 completed, 5 dupes merged, Active/Completed sub-tabs) and **granted milestone XP** (Kaelrath →
  L5). Funny beat: DM gave +50 XP each for romance with Talmarr — user let it ride. **86 tests pass.**
  Current campaign state: **the night before departing for the sister anchor** (north-northwest
  circled peak); next live beat = a scenic travel **montage** to the destination.
- 2026-06-03/04 — **PLAYED THE WHOLE ASCENSION TO ITS END** (the big one). Built the **INJECT system**
  (`broker.inject` + `/api/play/inject` + a `broker.recent` **replay buffer** so back-to-back pushed
  beats both survive a refresh — this was a real bug the user hit). Delivered the entire back half as
  **owner-authored cinematic beats** (write narrative → apply real state via DB → inject prose):
  treks to/from the sister anchor (claimed **Memory**), the **wall** (poured 8 max-HP of his own
  vitality in — Sacrifice down payment), the **wedding** to Talmarr, the **Creed** ("a god among men"),
  founding **The Kingdom of EmberHeart** + the **council titles** (Warden/Hearthkeeper/Forgemaster),
  the **mount system** (Cindermane), the Fire trek (claimed **Fire** = Sol-Thairn), the homecoming,
  the **prep-to-the-pyre montage** (Sella's reveal → Loremaster), and **THE SACRIFICE/REBIRTH** — all
  four domains united, reborn the God-Ascendant Flamekeeper, **still himself**. Plus a fire-country
  **14-day hunt** for ember-glass. Built **idle↔world material bridge**, **Inventory tab + tidy**, and
  fixed three real bugs: **idle-materials race/dupe** (MATERIAL_LOCK), **ITEM_REMOVE never depleted**
  (fuzzy match + qty), and the **economy starvation flaw** (production now scales with pop + divine
  grace). Patched a **"tak"→"tack" hallucination** in place. **97 tests pass.** Also used a background
  poller (`scripts/watch_council.py`, since deleted) to watch the live feed for a turn then act.
- 2026-06-04/05 — **KINGDOM-BUILDING phase, built with a 2nd agent (kimi).** Established the
  junior(kimi)/senior(me)/PM(user) workflow + lane discipline. I added the **`KINGDOM_CHANGE`**
  DM mechanic (DM moves the ledger from the story) and confirmed the DM already *reads* the ledger
  every turn. kimi built the **full kingdom dashboard** (4 sub-tabs, ~37-building catalog by
  category, prereq chains, construction projects, labor sliders, kingdom-chronicle); I **reviewed
  it** and caught + fixed the one real gap (building **ongoing effects were dead keys** — wired them
  into `economy.py`). Seeded the 3 pre-built buildings into the live (pre-dating) domain. Added a
  **smart `auto_labor()`** (⚡ button, priority bands, not an even split). Then 4 polish changes:
  **build ticks advance per play-beat**, **private companion chat uses the DM's model** (deepseek +
  intimate routing), the **DM slides into kingdom-building** (ruler's-day rhythm), and baked in the
  user's **COUNCIL MEETING FORMAT** (stats → advisor reports+proposals → debate → King's ruling).
  Also fixed a recurring **frontend cache gotcha** (no cache-bust on `/app.js` → hard-refresh /
  swipe-kill needed after any UI change; offered a `Cache-Control: no-cache` middleware, pending).
  **112 tests pass.** Campaign is in **post-ascension free play**: a living god ruling a thriving,
  fed kingdom.
- 2026-06-05 — Deep **post-ascension kingdom play** + features. kimi finished the **full building
  catalog** (37 buildings, prereqs, auto-build memorial, pre-seeded buildings) — I reviewed it (caught
  the dead-`ongoing`-keys gap, wired them), then added **`auto_labor()`** (⚡ smart split) and **multi-
  select suggestions** (toggle + "Do these N"). Fixed two real economy bugs: **"supplies" never produced**
  and the **pop-growth throttle** (pop_cap was a per-tick brake, not a ceiling → now a real `housing_cap`;
  user hard-capped pop ~12k). Built the **Gallery** (drop-a-file `frontend/gallery/` + tab + lightbox) and
  the user generated a gorgeous **canon art codex** (city aerial, gate, Kaelrath, Kaelrath-vs-Kryoss,
  vault, ember-glass panoply). STORY: introduced the **Empty Throne / Kryoss** void arc and brought
  **Vaelis Thorne** (old-party "wife", tiefling void-scholar) bursting into the council — reused the
  old corpus for her + seeded **consort-frame hooks** (Silvara/Mareth pending). Added the **ember-glass
  sword/panoply vision** to the journal. **114 tests pass.** Next: the user is about to play Vaelis in
  the Hearth-Hall; the Empty Throne is the live threat; the panoply is a forge-quest waiting.
- 2026-06-06/08 — **Big features + GO-LIVE.** STORY (via injects): codified **Ascendant Wings** (flight)
  vs **Flamewalk** (light-speed, loud) + the 3-tier divine-act cost curve; the **72h divine-steel gift
  forge**; the **3-week coronation montage** (claimed obsidian steel + dragon's gold, panoply forged but
  for the sun stone; deferred the **Sunken Caldera** void-trap as the next quest) → landed on **Day 82,
  eve of coronation** (user to play the crowning). Reintroduced the old-party "wives" as consort hooks
  (Vaelis ARRIVED & is tracked; Silvara/Mareth pending). ENGINE: **dynamic building catalog +
  `BUILDING_PROPOSE`**, **building upgrades** (`upgrades_from`/⬆ button), **Crews & Teams** system
  (`CREW_SET`, Labor-tab editor, DM-visible) + seeded 7 crews/3 buildings from the council's recital,
  a **Gallery** tab (drop-a-file canon art codex), **multi-select play suggestions**, **auto_labor**,
  **supplies fix**, **pop-growth `housing_cap` ceiling** (user hard-capped ~12k). **MIGRATED TO
  funiserver** with ~30s downtime (parallel build/test + tiny DB cutover), retired old origins, pulled
  models, wrote one-command **`scripts/deploy.sh`**, added **no-cache headers** + **iOS safe-area mobile
  fixes**. **117 tests pass.** Next: PLAY THE CORONATION on funiserver:8000, then the Sunken Caldera.
- 2026-06-08/09 — **Post-go-live polish + repo.** Mobile: **suggestions auto-fold when scrolling up to
  read** (return at bottom / on new beat). Made the **feed DB-backed** (`broker.recent` → `meta.feed_recent`
  + `restore_feed()` in lifespan) so injected/montage beats survive restarts/deploys, not just refreshes
  (verified: log says `restored N feed beats from disk`); had to RE-INJECT the coronation montage under the
  new code so it'd persist. Pushed source to a **PRIVATE GitHub repo `todell725/EHR`** — safety-checked the
  staging (caught that `/data/*.db` missed `data/backups|snapshots/`; switched to ignoring all of `/data/`;
  confirmed `.env` + DBs never left the Mac). **118 tests pass.** Still next: the user is about to PLAY THE
  CORONATION (Day 82) on funiserver:8000; then the Sunken-Caldera sun-stone quest + the Empty Throne arc.
- 2026-06-09 — **Two more code reviews triaged + acted (trust boundary hardened); quests fixed; Ollama saga.**
  Reviews → adversarial mechanics suite (found malformed-tag→`applied` bug), inject-through-`apply_mechanics`
  (split-brain fix), mid-stream narration recovery (`narrative_reset`), faction clamps, reembed script,
  condition dedup, RAG `to_thread`; pushed back on ORM/Alembic/SQL-fstring critiques with evidence.
  **Quests:** pruned 20→2 active (kept Forge the Sword of Legends + District Spokespersons), found+fixed
  **`QUEST_COMPLETE` silent no-op**, and **paid a 16-quest back-bounty** (+6,300 XP → L7-eligible, the **Seal
  of the Sixteen Deeds**, +16k treasury) via the inject-mechanics path. Added the quest **"↪ Pick this up"**
  button. **Big Ollama debugging:** "LLM unavailable: Connection error" traced to the **OllamaUI bundled
  image's dead WebUI healthcheck + autoheal recycling the container every ~2.5 min**; user swapped to plain
  `ollama/ollama` (no healthcheck), models persisted via `/mnt/user/Data/LLM`; intimate model swapped to
  **`dolphin3:8b`** (the 20B wouldn't pull — multi-stream network choke; single-stream throwaway container
  worked). **156 tests pass.** Verified all 4 model paths generate + the container is stable. STILL NEXT:
  PLAY THE CORONATION (now Day 83, coronation morning) on funiserver:8000; then the Sunken Caldera / Empty Throne.
