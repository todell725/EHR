"""Layer 1 — working memory (ephemeral, in-context).

Rebuilt fresh every turn from the structured-state layer. This is the compact
"here and now" block injected at the top of the prompt: where we are, when it is,
who's present, what's active, and the last few beats. It is never persisted — the
persistent layers are the source of truth.
"""

from __future__ import annotations

from backend.core import state


def _fmt_pc(pc: dict) -> str:
    ab = pc.get("abilities") or {}
    ab_str = " ".join(f"{k.upper()} {v}" for k, v in ab.items()) if ab else ""
    conds = pc.get("conditions") or []
    cond_str = (
        "; conditions: " + ", ".join(c.get("name", "?") for c in conds) if conds else ""
    )
    note = f" — {pc['notes']}" if pc.get("notes") else ""
    feats = pc.get("features") or []
    feat_str = ""
    if feats:
        names = ", ".join(f.get("name", "") for f in feats if f.get("name"))
        feat_str = f"\n    Actions/features: {names}"
    cd = pc.get("custom_dice") or {}
    dice_bits = [f"{k}={v}" for k, v in cd.items()
                 if k in ("sneak_attack", "psionic_power_die", "breath_weapon")]
    dice_str = f"\n    Combat dice: {', '.join(dice_bits)}" if dice_bits else ""
    return (
        f"- {pc['name']} (L{pc.get('level',1)} {pc.get('race','')} "
        f"{pc.get('class','')}): HP {pc.get('hp')}/{pc.get('max_hp')}, "
        f"AC {pc.get('ac')}{' | ' + ab_str if ab_str else ''}{cond_str}{note}{dice_str}{feat_str}"
    )


def build_full_context(recent_turns: list[dict] | None = None) -> str:
    """Whole-campaign context for large-window models (FULL_CONTEXT mode).

    Instead of RAG top-k, inject everything: the base scene block plus the entire
    chronicle, every open thread, the full NPC roster, and factions. With a big-window
    model this makes the DM omniscient about its own history — drift becomes impossible
    until the campaign outgrows the window.
    """
    from backend.core import db

    lines = [build_scene_block(recent_turns)]

    beats = db.query("SELECT id, content FROM chronicle ORDER BY id")
    if beats:
        lines.append("\n--- FULL CHRONICLE (every recorded beat, in order) ---")
        lines += [f"{b['id']}. {b['content']}" for b in beats]

    hooks = state.open_hooks()
    if hooks:
        lines.append("\n--- ALL OPEN THREADS ---")
        lines += [f"- (#{h['id']}) {h['description']}" for h in hooks]

    # exclude party companions (injected separately below), the dead, and resolved
    # phenomena ("gone") so the roster never double-lists someone like a recruited
    # Talmarr or clutters with a sealed wound. "entity" beings (the ley-anchor, the
    # grief-sentinel) stay — the DM should know they're present.
    npcs = [n for n in state.all_npcs(era="present")
            if n.get("status") not in ("party", "dead", "gone")]
    if npcs:
        lines.append("\n--- NPC ROSTER (in [MECHANICS], target anyone here by name OR by the "
                     "[id=...] shown — using the id is exact and never mis-resolves) ---")
        for n in npcs:
            head = f"{n['name']} ({n.get('role','')})".strip()
            if n.get("pronouns"):
                head += f" [{n['pronouns']}]"
            head += f" [id={n['id']}]"
            bits = [head]
            if n.get("disposition"):
                bits.append(f"disposition {n['disposition']}")
            for k in ("want", "need", "fear", "secret"):
                if n.get(k):
                    bits.append(f"{k}: {n[k]}")
            lines.append("- " + " | ".join(bits))

    facs = state.list_factions()
    if facs:
        lines.append("\n--- FACTIONS ---")
        lines += [f"- {f['name']} ({f.get('goal_tier')}), resources {f.get('resources')}"
                  for f in facs]

    return "\n".join(lines)


def _arc_note() -> str:
    """Optional DM-facing campaign-arc guidance (seeded once, injected every turn)."""
    from backend.core import db

    row = db.query_one("SELECT value FROM meta WHERE key = 'arc_note'")
    return (row["value"].strip() if row and row["value"] else "")


def _story_so_far() -> str:
    """Latest consolidated summary + recent chronicle beats — always-on grounding."""
    from backend.core import db

    parts: list[str] = []
    summ = db.query_one(
        "SELECT text FROM memory_chunks WHERE source = 'consolidation' "
        "ORDER BY id DESC LIMIT 1"
    )
    if summ and summ["text"]:
        parts.append("Summary: " + summ["text"].strip())
    beats = state.recent_chronicle(limit=6)
    if beats:
        parts.append("Recent beats:\n" + "\n".join(f"- {b['content']}" for b in beats))
    return "\n".join(parts)


def build_scene_block(recent_turns: list[dict] | None = None) -> str:
    """Assemble the WORLD STATE + PLAYER + RECENT HISTORY block for the prompt."""
    world = state.get_world()
    pcs = state.list_pcs()
    loc_id = world.get("location_id")
    present = state.list_npcs(location_id=loc_id) if loc_id else []

    loc_name = "an unknown place"
    if loc_id:
        from backend.core import db

        row = db.query_one("SELECT name FROM locations WHERE id = ?", [loc_id])
        if row:
            loc_name = row["name"]

    lines = [
        "--- WORLD STATE ---",
        f"Arc phase: {world.get('arc_phase','origins')}"
        f"{' (ruling a domain)' if world.get('domain_ruled') else ''}",
        f"Date: Year {world.get('year')}, {world.get('season')}, "
        f"day {world.get('day')} — {world.get('time_of_day')}; weather: {world.get('weather')}",
        f"Location: {loc_name}",
    ]
    # The maintained "current scene" — the single most important anti-drift anchor.
    scene = (world.get("scene") or "").strip()
    if scene:
        lines.append(f"CURRENT SCENE (stay consistent with this): {scene}")

    arc = _arc_note()
    if arc:
        lines.append("\n--- CAMPAIGN ARC (DM guidance — unfold GRADUALLY through play, never "
                     "dump it on the player) ---\n" + arc)
    globals_ = world.get("global_events") or []
    if globals_:
        lines.append("Active world events: " + "; ".join(str(g) for g in globals_))

    if present:
        lines.append("NPCs present: " + ", ".join(
            (f"{n['name']} ({n.get('role','')})".strip()
             + (f" [{n['pronouns']}]" if n.get("pronouns") else "")
             + f" [id={n['id']}]")
            for n in present
        ))

    # the camp's gathered stores — so the DM knows what's on hand and can let the player
    # USE it in the story (spend via MATERIAL_SPEND, award raw goods via MATERIAL_GAIN)
    stores = sorted(((k, int(v)) for k, v in state.get_materials().items() if v),
                    key=lambda kv: -kv[1])[:10]
    if stores:
        lines.append("CAMP STORES (gathered resources on hand — usable in-story): " +
                     "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in stores))

    # once a domain is ruled, the DM shifts from questing to RULERSHIP
    if world.get("domain_ruled"):
        from backend.sim import kingdom

        dom = kingdom.get_domain()
        if dom:
            stock = "; ".join(f"{k} {v}" for k, v in (dom.get("stockpiles") or {}).items())
            projects = dom.get("projects") or []
            proj_str = ("; under construction: " + ", ".join(
                f"{p.get('label', p.get('key'))} ({p.get('turns_left')} left)" for p in projects)
                if projects else "")
            lines.append(
                f"KINGDOM — {dom.get('name','the realm')}: pop {dom.get('population')}, "
                f"treasury {dom.get('treasury')}, military {dom.get('military')}, "
                f"morale {dom.get('morale')}/5" + (f"; stockpiles: {stock}" if stock else "")
                + proj_str + ".")
            crews = dom.get("crews") or []
            if crews:
                crew_str = "; ".join(
                    f"{c.get('name')} ({c.get('size')}" + (f", {c.get('role')}" if c.get('role') else "") + ")"
                    for c in crews)
                lines.append(
                    f"CREWS/TEAMS (the ruler's current assignments — honor these numbers, react to "
                    f"changes he makes, and use CREW_SET when the council stands up a new team): {crew_str}.")
            # The council roster is DATA-DRIVEN (from npcs.council) so appointments the
            # King makes in play survive any narration model — fall back to the founding
            # four only if nobody is seated yet. Queen Talmarr is rendered separately as
            # co-ruler, so she is not seated as an ordinary councillor.
            council = state.list_council()
            if council:
                advisor_names = ", ".join(c["name"] for c in council)
                advisor_bullets = "".join(
                    f"   • {c['name']} → {c.get('council') or c.get('role', '')}\n"
                    for c in council)
            else:
                advisor_names = ("Warden Renn, Hearthkeeper Orina, Forgemaster Bheric, "
                                 "Loremaster Sella")
                advisor_bullets = (
                    "   • Warden Renn → defense, the watch, the walls, the army, border threats\n"
                    "   • Hearthkeeper Orina → food, health, morale, the commonfolk's needs, rations\n"
                    "   • Forgemaster Bheric → building, industry, the forge, construction, resources\n"
                    "   • Loremaster Sella → lore, omens, the deep past, ley/void threats, the EmberHeart\n")
            lines.append(
                "--- KINGDOM-BUILDING MODE (the arc has shifted from questing to RULERSHIP) ---\n"
                "The hero is now the God-Ascendant Flamekeeper, a king ruling EmberHeart. Slide the "
                "story OUT of lone gritty questing and INTO running a kingdom. Frame the rhythm of a "
                "ruler's day: the King WAKES, holds a COUNCIL MEETING with his queen Talmarr and his "
                f"advisors ({advisor_names}), "
                "then TACKLES THE DAY'S PROBLEMS — petitions and disputes, building and supply "
                "decisions, the people's needs, threats at the borders, the realm's prosperity. Treat "
                "the KINGDOM ledger above as real stakes and MOVE it with KINGDOM_CHANGE when the "
                "day's events warrant. Adventures still happen, but they now arrive AS the kingdom's "
                "concerns brought to the throne — not the hero wandering off alone.\n"
                "COUNCIL MEETING FORMAT (use this structure whenever the King holds council):\n"
                "1. OPEN with a brief State of the Realm — the current kingdom stats (pop, treasury, "
                "military, morale, stockpiles, anything under construction).\n"
                "2. Each advisor gives a short REPORT on their own domain, then brings ONE concrete "
                "PROPOSAL for it:\n"
                f"{advisor_bullets}"
                "   • Queen Talmarr → co-ruler; weighs in broadly, scouting, and the human cost\n"
                "   Also surface noble proposals, public petitions/needs, and district/building upgrades.\n"
                "3. The council may REACT to each other — agree, object, weigh the cost, debate.\n"
                "4. END by laying the decisions before the King and STOPPING for KAELRATH (the player) "
                "to give the FINAL RULING. Do NOT decide for him — present the choices in [SUGGESTIONS] "
                "and wait. Apply the consequences of his rulings with KINGDOM_CHANGE / building tags.\n"
                "APPOINTMENTS: when the King raises someone to the council (or removes them), you MUST "
                "declare it with COUNCIL_APPOINT: <name>, <portfolio> (or COUNCIL_DISMISS: <name>). The "
                "advisor roster above is built from these tags — an appointment only sticks if tagged.")

    # STORY SO FAR — always injected so the thread is never lost, even past the
    # working-memory window. Latest consolidation summary + recent chronicle beats.
    story = _story_so_far()
    if story:
        lines.append("\n--- STORY SO FAR (established facts — do not contradict) ---")
        lines.append(story)

    mounts = state.list_mounts(active_only=True)
    if mounts:
        lines.append("MOUNTS (ridden/bonded — use them in travel & battle): " + "; ".join(
            f"{m['name']} ({m.get('kind','mount')}, HP {m.get('hp')}/{m.get('max_hp')}"
            + (", " + ", ".join(m['traits']) if m.get('traits') else "") + ")"
            for m in mounts))

    heroes = [p for p in pcs if p.get("is_player", 1)]
    companions = [p for p in pcs if not p.get("is_player", 1)]
    lines.append("\n--- THE HERO (the player controls — address as 'you') ---")
    lines += [_fmt_pc(pc) for pc in heroes] or ["(none created yet)"]
    if companions:
        lines.append("\n--- PARTY COMPANIONS (YOU the DM voice & act them; the player only "
                     "manages their sheets. For disposition/status tags, target the [id=...] "
                     "shown — it points at their character record) ---")
        for pc in companions:
            line = _fmt_pc(pc)
            onpc = state.find_npc_by_name(pc["name"])
            if onpc:
                line += f"  [id={onpc['id']}]"
            lines.append(line)

    if recent_turns:
        lines.append("\n--- RECENT HISTORY (most recent last) ---")
        for t in recent_turns[-7:]:
            who = t.get("actor", "Player")
            lines.append(f"{who}: {t.get('player','')}")
            if t.get("dm"):
                snippet = t["dm"].strip().replace("\n", " ")
                lines.append(f"DM: {snippet[:280]}")

    return "\n".join(lines)
