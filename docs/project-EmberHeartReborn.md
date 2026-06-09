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
**97 tests pass**; SCHEMA_VERSION=8; `.venv` is **Python 3.12** (not the 3.14 system default).
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
- **Memory = SQLite + numpy brute-force cosine** (corpus <10k chunks → no vector server/Chroma).
  Embeddings via `nomic-embed-text` (768-dim). **Never change the embed model once populated** —
  mixing breaks cosine; the `dims` column is the tripwire.
- **Output contract:** four sections `[NARRATIVE]/[MECHANICS]/[SUGGESTIONS]/[CHRONICLE]`. LLM
  *declares* changes via tags; deterministic Python *applies* them; **Python owns all dice.**
  `STRICT_OUTPUT=true` switches to a guaranteed-parseable JSON contract (escape hatch for model
  drift) at the cost of live streaming.
- Deploy target funiserver via Docker (`host.docker.internal` for Ollama, uid 99:100). `.env`
  not in git; `data/` (live campaign DB) never clobbered by deploy.
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
