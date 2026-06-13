-- EmberHeart Reborn — canonical SQLite schema.
-- One file holds structured state + chronicle + vector memory. The LLM READS
-- this; only the deterministic Python layer WRITES it (from parsed [MECHANICS]).
-- All statements are idempotent so this can run on every boot.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- world_state
-- Singleton (id = 1). The living world's clock and global condition.
CREATE TABLE IF NOT EXISTS world_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    arc_phase       TEXT    NOT NULL DEFAULT 'origins',   -- 'origins' | 'kingdom'
    domain_ruled    INTEGER NOT NULL DEFAULT 0,           -- bool; flips on the economy tick
    year            INTEGER NOT NULL DEFAULT 1,
    month           INTEGER NOT NULL DEFAULT 1,
    day             INTEGER NOT NULL DEFAULT 1,
    season          TEXT    NOT NULL DEFAULT 'The Sowing',
    time_of_day     TEXT    NOT NULL DEFAULT 'morning',
    weather         TEXT    NOT NULL DEFAULT 'clear',
    location_id     TEXT,                                 -- current party location
    global_events   TEXT    NOT NULL DEFAULT '[]',        -- json array of active global events
    turn_counter    INTEGER NOT NULL DEFAULT 0,
    updated_at      REAL    NOT NULL DEFAULT (unixepoch('subsec'))
);

-- ----------------------------------------------------------- player_characters
CREATE TABLE IF NOT EXISTS player_characters (
    id           TEXT    PRIMARY KEY,
    name         TEXT    NOT NULL,
    race         TEXT,
    class        TEXT,
    subclass     TEXT,
    level        INTEGER NOT NULL DEFAULT 1,
    xp           INTEGER NOT NULL DEFAULT 0,
    hp           INTEGER NOT NULL DEFAULT 10,
    max_hp       INTEGER NOT NULL DEFAULT 10,
    ac           INTEGER NOT NULL DEFAULT 10,
    abilities    TEXT    NOT NULL DEFAULT '{}',  -- {str,dex,con,int,wis,cha}
    conditions   TEXT    NOT NULL DEFAULT '[]',  -- [{name, rounds}]
    inventory    TEXT    NOT NULL DEFAULT '[]',  -- [{item, qty}]
    skills       TEXT    NOT NULL DEFAULT '{}',  -- idle-skill levels {mining: 12, ...}
    custom_dice  TEXT    NOT NULL DEFAULT '{}',  -- {psionic: 'd6', sneak_attack: 2}
    status       TEXT    NOT NULL DEFAULT 'alive',
    notes        TEXT    NOT NULL DEFAULT '',
    is_player    INTEGER NOT NULL DEFAULT 1
);

-- ----------------------------------------------------------------------- npcs
CREATE TABLE IF NOT EXISTS npcs (
    id           TEXT    PRIMARY KEY,            -- e.g. EH-01, or generated NPC-<uuid>
    name         TEXT    NOT NULL,
    race         TEXT,
    role         TEXT,
    faction_id   TEXT REFERENCES factions(id) ON DELETE SET NULL,
    location_id  TEXT REFERENCES locations(id) ON DELETE SET NULL,
    domains      TEXT    NOT NULL DEFAULT '[]',  -- expertise tags for the router
    personality  TEXT    NOT NULL DEFAULT '[]',  -- 3-5 traits
    secret       TEXT,
    want         TEXT,                            -- immediate desire
    need         TEXT,                            -- deeper motivation
    fear         TEXT,
    bio          TEXT    NOT NULL DEFAULT '',
    motivation   TEXT    NOT NULL DEFAULT '',
    disposition  TEXT    NOT NULL DEFAULT '{}',  -- {PC-01: 40, ...} toward each PC
    status       TEXT    NOT NULL DEFAULT 'alive',-- alive | dead | missing
    council      TEXT    NOT NULL DEFAULT '',     -- portfolio if seated on the King's council; '' = not a councillor
    seed         INTEGER NOT NULL DEFAULT 0,      -- came from ingested corpus
    era          TEXT    NOT NULL DEFAULT 'present' -- 'present' | 'future_foreshadow'
);

-- ------------------------------------------------------------------- factions
CREATE TABLE IF NOT EXISTS factions (
    id            TEXT    PRIMARY KEY,
    name          TEXT    NOT NULL,
    goal_tier     TEXT    NOT NULL DEFAULT 'survival', -- survival|consolidation|expansion|dominance
    goals         TEXT    NOT NULL DEFAULT '[]',
    resources     INTEGER NOT NULL DEFAULT 10,
    leaders       TEXT    NOT NULL DEFAULT '[]',  -- npc ids
    relationships TEXT    NOT NULL DEFAULT '{}',  -- {faction_id: score}
    reputation    TEXT    NOT NULL DEFAULT '{}',  -- {PC-01: score} player standing
    threat_list   TEXT    NOT NULL DEFAULT '[]',
    notes         TEXT    NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------------ locations
CREATE TABLE IF NOT EXISTS locations (
    id                    TEXT    PRIMARY KEY,
    name                  TEXT    NOT NULL,
    region                TEXT,
    discovered            INTEGER NOT NULL DEFAULT 0,
    features              TEXT    NOT NULL DEFAULT '[]',
    controlling_faction   TEXT REFERENCES factions(id) ON DELETE SET NULL,
    danger_level          INTEGER NOT NULL DEFAULT 1,
    description           TEXT    NOT NULL DEFAULT ''
);

-- --------------------------------------------------------------------- quests
CREATE TABLE IF NOT EXISTS quests (
    id           TEXT    PRIMARY KEY,
    title        TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'active', -- active|completed|failed
    giver        TEXT,
    objectives   TEXT    NOT NULL DEFAULT '[]',     -- [{text, complete}]
    deadline     TEXT,                              -- in-world date 'Y-M-D' or null
    rewards      TEXT    NOT NULL DEFAULT '[]',
    description  TEXT    NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------- world_hooks
-- Chekhov's-arsenal seeds: planted details that should pay off later.
CREATE TABLE IF NOT EXISTS world_hooks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    description  TEXT    NOT NULL,
    payoff_hint  TEXT    NOT NULL DEFAULT '',
    planted_turn INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'seeded', -- seeded|paying_off|resolved
    related      TEXT    NOT NULL DEFAULT '[]'
);

-- ------------------------------------------------------------------ chronicle
-- Timestamped significant beats. Source for "Previously on" + RAG retrieval.
CREATE TABLE IF NOT EXISTS chronicle (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL    NOT NULL DEFAULT (unixepoch('subsec')),
    in_world_date  TEXT    NOT NULL DEFAULT '',
    content        TEXT    NOT NULL,
    tags           TEXT    NOT NULL DEFAULT '[]',
    npcs_involved  TEXT    NOT NULL DEFAULT '[]',
    significant    INTEGER NOT NULL DEFAULT 1,
    session_id     INTEGER REFERENCES sessions(id) ON DELETE SET NULL
);

-- -------------------------------------------------------------- memory_chunks
-- Layer-2 semantic memory. embedding stored as raw float32 bytes (see rag.py).
CREATE TABLE IF NOT EXISTS memory_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,            -- lore|npc|quest|faction|location|chronicle|session|note
    ref_id      TEXT,                        -- id of the source row, if any
    source      TEXT    NOT NULL DEFAULT '', -- provenance (file path / 'play')
    text        TEXT    NOT NULL,
    embedding   BLOB,                        -- float32 vector; null until embedded
    dims        INTEGER,                     -- vector length (sanity check)
    era         TEXT    NOT NULL DEFAULT 'present', -- 'present' | 'future_foreshadow'
    seed        INTEGER NOT NULL DEFAULT 0,
    created_at  REAL    NOT NULL DEFAULT (unixepoch('subsec'))
);
CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_chunks(kind);
CREATE INDEX IF NOT EXISTS idx_memory_era  ON memory_chunks(era);

-- ------------------------------------------------------------------- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      INTEGER NOT NULL,
    started_at  REAL    NOT NULL DEFAULT (unixepoch('subsec')),
    ended_at    REAL,
    turns       INTEGER NOT NULL DEFAULT 0,
    summary     TEXT    NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------ combat_encounters
-- At most one row with status='active' at a time.
CREATE TABLE IF NOT EXISTS combat_encounters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    status        TEXT    NOT NULL DEFAULT 'active', -- active|ended
    round         INTEGER NOT NULL DEFAULT 1,
    turn_index    INTEGER NOT NULL DEFAULT 0,
    participants  TEXT    NOT NULL DEFAULT '[]',  -- [{id,name,side,hp,max_hp,ac,init,zone,ai,conditions,down,death_saves}]
    log           TEXT    NOT NULL DEFAULT '[]',
    started_at    REAL    NOT NULL DEFAULT (unixepoch('subsec'))
);

-- ------------------------------------------------------------------- meta kv
CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
