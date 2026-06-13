"""The DM turn loop — Chronicle Weaver orchestration.

Per turn:
  1. assemble context = working memory + semantic recall + relevant NPCs + dice from
     the previous turn ("rolls are injected into the next prompt");
  2. call Ollama (hot temp) and stream the raw response;
  3. parse the four-section contract (retry once, cold, if it fails);
  4. apply [MECHANICS] deterministically (rolling any new dice);
  5. write the chronicle beat back into semantic memory; consolidate every N turns.

`stream_turn` is an async generator of UI events; `take_turn` is the buffered wrapper.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import AsyncIterator

from backend.core import backups, db, state
from backend.core.config import settings
from backend.core.models import RollResult
from backend.dm import mechanics, parser, prompt, router, routing
from backend.llm.client import get_llm
from backend.memory import consolidate, rag, working

logger = logging.getLogger("emberheart.dm")

# Layer-1 ephemeral history (lost on restart by design).
_recent_turns: deque[dict] = deque(maxlen=10)


def clear_recent() -> None:
    """Reset ephemeral working-memory history (e.g. after an undo)."""
    _recent_turns.clear()


# ------------------------------------------------------------- pending dice (durable)
def _load_pending() -> list[RollResult]:
    row = db.query_one("SELECT value FROM meta WHERE key = 'pending_rolls'")
    if not row:
        return []
    try:
        return [RollResult(**d) for d in json.loads(row["value"])]
    except Exception:  # noqa: BLE001
        return []


def _save_pending(rolls: list[RollResult]) -> None:
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('pending_rolls', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [json.dumps([r.model_dump() for r in rolls])],
    )


def _load_pending_combat() -> list[str]:
    row = db.query_one("SELECT value FROM meta WHERE key = 'pending_combat'")
    try:
        return json.loads(row["value"]) if row else []
    except Exception:  # noqa: BLE001
        return []


def _save_pending_combat(lines: list[str]) -> None:
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('pending_combat', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [json.dumps(lines)],
    )


# ------------------------------------------------------------------------ session
def ensure_session() -> int:
    row = db.query_one("SELECT value FROM meta WHERE key = 'session_id'")
    if row:
        return int(row["value"])
    num = (db.query_one("SELECT COALESCE(MAX(number),0) n FROM sessions")["n"]) + 1
    sid = db.execute("INSERT INTO sessions (number) VALUES (?)", [num]).lastrowid
    db.execute(
        "INSERT INTO meta (key, value) VALUES ('session_id', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [str(sid)],
    )
    return sid


def previously_on() -> str:
    beats = state.recent_chronicle(limit=5)
    return " ".join(b["content"] for b in beats)


async def _flesh_npc(nid: str) -> None:
    """Best-effort: generate a dossier (secret/want/need/fear) for a spawned NPC."""
    npc = state.get_npc(nid)
    if not npc:
        return
    try:
        raw = await asyncio.wait_for(
            get_llm().chat(
                [
                    {"role": "system", "content":
                        "Return ONLY a JSON object with keys: pronouns (e.g. 'she/her', "
                        "'he/him', 'they/them'), personality (array of 3-5 short traits), "
                        "secret, want, need, fear, bio (1-2 sentences). Dark frontier fantasy tone."},
                    {"role": "user", "content":
                        f"Flesh out this EmberHeart origins-era NPC: name={npc['name']}, "
                        f"role={npc.get('role','')}."},
                ],
                mode="adjudication", response_format={"type": "json_object"},
            ),
            timeout=settings.narration_timeout,   # decorative call must never hang the turn
        )
        d = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        upd: dict = {"id": nid}
        for key in ("pronouns", "secret", "want", "need", "fear", "bio"):
            if d.get(key):
                upd[key] = str(d[key])
        if isinstance(d.get("personality"), list):
            upd["personality"] = [str(x) for x in d["personality"][:5]]
        state.upsert_npc(upd)
    except Exception as exc:  # noqa: BLE001 - decorative, never block the turn
        logger.warning("npc fill failed for %s: %s", nid, exc)


# --------------------------------------------------------------------- turn loop
_bg_tasks: set = set()

# Models we've already gotten a response from this process — they skip the cold-start
# grace budget. Warming a model on session start populates this up front.
_warmed: set[str] = set()


def _timeout_for(model: str) -> float:
    """Cold-start grace until a model has produced once; snappy budget thereafter."""
    return settings.narration_timeout if model in _warmed else settings.cold_start_timeout


# Characters that legitimately END a finished beat: sentence punctuation, closing
# quotes/brackets, an em-dash or italics cliffhanger. Anything else trailing — a bare
# letter, a comma, a colon — means the stream was cut mid-thought, not closed.
_TERMINAL_PUNCT = set('.!?…"\'“”‘’*)]}>—-')


def _looks_truncated(text: str | None) -> bool:
    """True if narration ends mid-thought — a cloud model can close the stream cleanly
    (no error) yet stop mid-word, so _narrate's mid-stream recovery never fires. We catch
    it here and regenerate. Too-short beats are the garbled-guard's job, not ours."""
    t = (text or "").rstrip()
    if len(t) < 20:
        return False
    return t[-1] not in _TERMINAL_PUNCT


def mark_warm(model: str) -> None:
    if model:
        _warmed.add(model)


async def warm_model(model: str | None = None) -> bool:
    """Preload a model with a tiny request so its first real turn isn't a cold start."""
    model = model or settings.narration_model
    if model in _warmed:
        return True
    try:
        await get_llm().chat(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            mode="adjudication", model=model,
        )
        mark_warm(model)
        logger.info("warmed model %s", model)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("warmup failed for %s: %s", model, exc)
        return False


async def _aclose_quietly(ait) -> None:
    try:
        await ait.aclose()
    except Exception:  # noqa: BLE001
        pass


def _abandon(ait) -> None:
    """Close a stalled stream in the background so we don't block on draining it."""
    task = asyncio.create_task(_aclose_quietly(ait))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _narrate(messages, primary: str, fallback: str, ttft: float):
    """Stream narration deltas, dropping to `fallback` if `primary` doesn't produce a
    first token within `ttft` seconds (or errors). Yields ('fallback', model) once if it
    switches, then ('delta', text) repeatedly."""
    llm = get_llm()
    ait = llm.stream_chat(messages, mode="narration", model=primary).__aiter__()
    fell_back = False
    first = None
    try:
        first = await asyncio.wait_for(ait.__anext__(), timeout=ttft)
    except StopAsyncIteration:
        return
    except BaseException as exc:  # noqa: BLE001 - timeout OR transport error -> fall back
        logger.warning("primary narration '%s' slow/failed (%s)", primary, exc)
        _abandon(ait)  # fire-and-forget; don't block the fallback on connection drain
        if not fallback or fallback == primary:
            raise
        fell_back = True

    if not fell_back:
        yield ("delta", first)
        try:
            async for d in ait:
                yield ("delta", d)
            return
        except BaseException as exc:  # noqa: BLE001 - mid-stream transport drop (cloud models do this)
            logger.warning("primary narration '%s' dropped mid-stream (%s)", primary, exc)
            _abandon(ait)
            if not fallback or fallback == primary:
                raise
            # discard the partial and regenerate cleanly on the fallback (consumer resets display)
            yield ("reset", fallback)
            async for d in llm.stream_chat(messages, mode="narration", model=fallback):
                yield ("delta", d)
            return

    yield ("fallback", fallback)
    async for d in llm.stream_chat(messages, mode="narration", model=fallback):
        yield ("delta", d)


async def stream_turn(action: str, pc_id: str | None = None) -> AsyncIterator[dict]:
    session_id = ensure_session()

    # Safety net: snapshot state BEFORE this turn mutates anything, so "undo last
    # turn" can roll back cleanly even if the turn goes sideways.
    try:
        backups.pre_turn_snapshot(state.get_world().get("turn_counter", 0) + 1)
    except Exception as exc:  # noqa: BLE001 - never let backups block play
        logger.warning("pre-turn snapshot failed: %s", exc)

    turn_no = state.bump_turn()
    world = state.get_world()

    pending = _load_pending()
    pending_combat = _load_pending_combat()
    full_ctx = settings.full_context

    # FULL_CONTEXT stuffs the whole campaign; lean mode uses RAG top-k + recent hooks.
    if full_ctx:
        retrieved = []
        scene = working.build_full_context(list(_recent_turns))
        hooks: list[str] = []  # already embedded in the full-context block
    else:
        retrieved = await rag.retrieve(action)
        scene = working.build_scene_block(list(_recent_turns))
        hooks = [h["description"] for h in state.open_hooks(limit=8)]

    npcs = router.select_npcs(action, location_id=world.get("location_id"))
    briefs = [router.npc_brief(n) for n in npcs]
    previously = previously_on() if not _recent_turns else None

    # content-aware model routing: mature beats -> uncensored local model
    narration_model, intimate_route = routing.pick_narration_model(action, world.get("scene", ""))
    used_model = narration_model  # may change via fallback / reactive intimate routing

    strict = settings.strict_output
    system = prompt.build_system_prompt(strict_json=strict)
    user = prompt.build_user_prompt(
        action=action, scene_block=scene, retrieved=retrieved,
        npc_briefs=briefs, roll_results=pending, previously=previously,
        combat_log=pending_combat, open_hooks=hooks,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    yield {"type": "start", "turn": turn_no,
           "mode": "strict" if strict else "stream", "model": narration_model}

    fallback_model = settings.fallback_model
    if strict:
        # Buffered structured call — guaranteed-parseable, but no live token stream.
        async def _strict_call(model: str) -> str:
            return await get_llm().chat(
                messages, mode="narration", model=model,
                response_format={"type": "json_object"},
            )
        try:
            full = await asyncio.wait_for(
                _strict_call(narration_model), timeout=_timeout_for(narration_model)
            )
            mark_warm(narration_model)
        except BaseException as exc:  # noqa: BLE001 - slow or failed -> fall back
            if fallback_model and fallback_model != narration_model:
                logger.warning("strict primary '%s' slow/failed (%s); falling back to '%s'",
                               narration_model, exc, fallback_model)
                yield {"type": "notice",
                       "message": f"Primary model slow — switched to {fallback_model}."}
                try:
                    full = await _strict_call(fallback_model)
                    used_model = fallback_model
                except Exception as exc2:  # noqa: BLE001
                    yield {"type": "error", "message": f"LLM unavailable: {exc2}"}
                    return
            else:
                yield {"type": "error", "message": f"LLM unavailable: {exc}"}
                return
        parsed = parser.parse_json(full)
        if not parsed.parse_ok:
            try:
                full = await get_llm().chat(
                    messages + [{"role": "user",
                                 "content": "Return ONLY the JSON object as specified."}],
                    mode="adjudication", response_format={"type": "json_object"},
                )
                p2 = parser.parse_json(full)
                if p2.parse_ok:
                    parsed = p2
            except Exception as exc:  # noqa: BLE001
                logger.error("strict repair failed: %s", exc)
        if parsed.narrative:
            yield {"type": "token", "text": parsed.narrative}
    else:
        # stream tokens, but only the *display-safe* narrative (headers/mechanics hidden).
        # _narrate falls back to a local model if the primary stalls on first token.
        full = ""
        shown = 0
        primary_active = True
        try:
            async for kind, val in _narrate(
                messages, narration_model, fallback_model, _timeout_for(narration_model)
            ):
                if kind == "fallback":
                    primary_active = False
                    used_model = val
                    yield {"type": "notice",
                           "message": f"Primary model slow — switched to {val}."}
                    full, shown = "", 0  # restart accumulation for the fallback stream
                    continue
                if kind == "reset":
                    # primary dropped mid-stream: wipe the partial text already on screen and
                    # restart cleanly on the fallback (no half-narration left dangling)
                    primary_active = False
                    used_model = val
                    full, shown = "", 0
                    yield {"type": "narrative_reset"}
                    yield {"type": "notice",
                           "message": f"Primary dropped mid-stream — regenerating on {val}."}
                    continue
                if primary_active and not full:
                    mark_warm(narration_model)  # primary produced -> it's warm now
                full += val
                vis, _ = parser.streaming_narrative(full)
                if len(vis) > shown:
                    yield {"type": "token", "text": vis[shown:]}
                    shown = len(vis)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM stream failed: %s", exc)
            yield {"type": "error", "message": f"LLM unavailable: {exc}"}
            return

        vis, _ = parser.streaming_narrative(full)  # flush any trailing narrative
        if len(vis) > shown:
            yield {"type": "token", "text": vis[shown:]}

        parsed = parser.parse(full)

        # one cold REPAIR pass — reformat existing prose rather than regenerating.
        if not parsed.parse_ok:
            logger.warning("parse failed (%s); repairing once", parsed.parse_notes)
            try:
                repaired = await get_llm().chat(
                    [
                        {"role": "system", "content": (
                            "Reformat the text below into EXACTLY four sections with "
                            "these headers on their own lines: [NARRATIVE], [MECHANICS], "
                            "[SUGGESTIONS], [CHRONICLE]. Keep the prose verbatim in "
                            "[NARRATIVE]. [MECHANICS] holds machine tags only (or 'none')."
                        )},
                        {"role": "user", "content": full or action},
                    ],
                    mode="adjudication",
                )
                repaired_parsed = parser.parse(repaired)
                if repaired_parsed.parse_ok:
                    parsed = repaired_parsed
            except Exception as exc:  # noqa: BLE001
                logger.error("repair failed: %s", exc)

        # Truncation guard: a cloud model can end the stream cleanly but mid-thought
        # (stops mid-word), so no exception fires and _narrate's mid-stream recovery never
        # triggers. Detect a beat that doesn't close on terminal punctuation and regenerate
        # ONCE on the fallback. Only when the PRIMARY produced it — never loop on the fallback.
        if (primary_active and fallback_model and fallback_model != narration_model
                and _looks_truncated(parsed.narrative)):
            logger.warning("narration truncated mid-thought (...%r); regenerating on %s",
                           (parsed.narrative or "")[-30:], fallback_model)
            yield {"type": "narrative_reset"}
            yield {"type": "notice",
                   "message": f"Beat cut short mid-stream — regenerating on {fallback_model}."}
            used_model = fallback_model
            full, shown = "", 0
            try:
                async for d in get_llm().stream_chat(
                        messages, mode="narration", model=fallback_model):
                    full += d
                    vis, _ = parser.streaming_narrative(full)
                    if len(vis) > shown:
                        yield {"type": "token", "text": vis[shown:]}
                        shown = len(vis)
            except Exception as exc:  # noqa: BLE001
                logger.error("truncation-regeneration on %s failed: %s", fallback_model, exc)
            vis, _ = parser.streaming_narrative(full)
            if len(vis) > shown:
                yield {"type": "token", "text": vis[shown:]}
            parsed = parser.parse(full)

    # reactive content routing: if the primary model refused a mature beat, regenerate
    # on the uncensored model and swap in its narrative.
    if (settings.route_intimate and not intimate_route and settings.intimate_model
            and routing.looks_like_refusal(parsed.narrative or full)):
        logger.info("primary model appears to have refused; routing to intimate model")
        try:
            redo = await get_llm().chat(messages, mode="narration", model=settings.intimate_model)
            reparsed = parser.parse_json(redo) if strict else parser.parse(redo)
            if reparsed.parse_ok:
                parsed = reparsed
                used_model = settings.intimate_model
                yield {"type": "narrative_reset"}   # clear the refused text, don't append to it
                yield {"type": "token", "text": parsed.narrative}
        except Exception as exc:  # noqa: BLE001
            logger.warning("intimate fallback failed: %s", exc)

    # guard: a choking model (especially a small fallback fed a huge FULL_CONTEXT prompt) can
    # emit empty or junk narration like "###". NEVER commit that as a beat — it corrupts the
    # scene and burns the turn. Fail cleanly so the player just retries (deepseek usually recovers).
    if len((parsed.narrative or "").strip()) < 20:
        logger.warning("rejecting garbled narration (%r) from %s", (parsed.narrative or "")[:40], used_model)
        yield {"type": "error",
               "message": "The Weaver's words came out garbled (model hiccup) — try that action again."}
        return

    # apply mechanics deterministically
    mech = mechanics.apply_mechanics(parsed.mechanics, acting_pc_id=pc_id)

    # ---- combat integration: start / resolve enemy turns / end ----------------
    from backend.sim import combat as combat_engine

    combat_lines: list[str] = []
    if mech.get("combat_start"):
        enemies = mech.get("combat_enemies") or [
            {"name": "Lurking Threat", "hp": 9, "ac": 12, "ai": "berserker"}
        ]
        try:
            enc = combat_engine.start_combat(enemies)
            combat_lines += enc.get("log", [])
            combat_lines += combat_engine.advance_to_player().get("log", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("combat start failed: %s", exc)
    elif combat_engine.status() is not None:
        # an active fight: the player has acted — resolve enemy/death-save turns
        try:
            combat_lines += combat_engine.end_player_turn().get("log", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("combat advance failed: %s", exc)
    if mech.get("combat_end"):
        combat_engine.end_combat()
    _save_pending_combat(combat_lines)

    # flesh out any NPCs the DM spawned so they stay consistent in later scenes
    for nid in mech.get("spawned", []):
        await _flesh_npc(nid)

    # anti-drift: keep CURRENT SCENE fresh every turn. If the DM emitted SCENE_SET it
    # already won; otherwise derive the anchor from the opening line of the narrative
    # (present-tense, "where we are now") so the scene block never goes stale or empty.
    if not any(m.tag == "SCENE_SET" for m in parsed.mechanics) and parsed.narrative:
        first = parsed.narrative.strip().replace("\n", " ").split(". ")[0]
        if first:
            state.update_world(scene=first[:200])

    # time advance via the calendar (sim module; tolerated if absent)
    if mech.get("time_advance"):
        try:
            from backend.sim import calendar

            amount, unit = mech["time_advance"]
            calendar.advance(amount, unit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("calendar advance skipped: %s", exc)

    # chronicle write-back -> semantic memory
    if parsed.chronicle:
        w = state.get_world()
        date = f"Y{w.get('year')}-{w.get('season')}-d{w.get('day')}"
        state.add_chronicle(parsed.chronicle, in_world_date=date,
                            npcs=[n["id"] for n in npcs], session_id=session_id)
        await rag.remember(parsed.chronicle, kind="chronicle")

    # dice rolled THIS turn are injected into the NEXT turn
    _save_pending(mech.get("rolls", []))

    # update ephemeral history + session turn count
    _recent_turns.append({"player": action, "dm": parsed.narrative,
                          "actor": pc_id or "Player"})
    db.execute("UPDATE sessions SET turns = turns + 1 WHERE id = ?", [session_id])

    # once a domain is ruled, construction advances one tick per beat — building progress
    # now keeps pace with the story instead of needing a manual button
    if state.get_world().get("domain_ruled"):
        try:
            from backend.sim import kingdom

            kingdom.tick_projects()
        except Exception as exc:  # noqa: BLE001
            logger.warning("project tick skipped: %s", exc)

    # periodic consolidation
    if consolidate.should_consolidate(turn_no):
        try:
            await consolidate.consolidate_recent()
        except Exception as exc:  # noqa: BLE001
            logger.warning("consolidation skipped: %s", exc)

    yield {
        "type": "result",
        "turn": turn_no,
        "narrative": parsed.narrative,
        "suggestions": [s.model_dump() for s in parsed.suggestions],
        "chronicle": parsed.chronicle,
        "applied": mech.get("applied", []),
        "rejected": mech.get("rejected", []),
        "notes": mech.get("notes", []),
        "rolls": [r.model_dump() for r in mech.get("rolls", [])],
        "combat_start": mech.get("combat_start", False),
        "combat_end": mech.get("combat_end", False),
        "combat": combat_engine.status(),
        "combat_log": combat_lines,
        "parse_notes": parsed.parse_notes,
        "model": used_model,
    }


async def take_turn(action: str, pc_id: str | None = None) -> dict:
    """Buffered (non-streaming) turn — collects the stream into a final result."""
    result: dict = {}
    async for event in stream_turn(action, pc_id):
        if event["type"] == "result":
            result = event
        elif event["type"] == "error":
            return {"type": "error", "message": event["message"]}
    return result


async def end_session() -> dict:
    """Summarize the session, flag open threads, and close it out."""
    row = db.query_one("SELECT value FROM meta WHERE key = 'session_id'")
    if not row:
        return {"ok": False, "detail": "no active session"}
    session_id = int(row["value"])

    beats = state.recent_chronicle(limit=20)
    summary = ""
    if beats:
        joined = "\n".join(f"- {b['content']}" for b in beats)
        try:
            summary = await get_llm().chat(
                [
                    {"role": "system", "content":
                        "You are the campaign archivist. Write a 3-6 sentence end-of-session "
                        "summary: key events, decisions, consequences, and unresolved threads."},
                    {"role": "user", "content": f"This session's beats:\n{joined}"},
                ],
                mode="adjudication",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("session summary failed: %s", exc)

    open_hooks = [h["description"] for h in state.open_hooks()]
    open_quests = [q["title"] for q in state.list_quests(status="active")]

    db.execute(
        "UPDATE sessions SET ended_at = unixepoch('subsec'), summary = ? WHERE id = ?",
        [summary, session_id],
    )
    db.execute("DELETE FROM meta WHERE key = 'session_id'")  # next start opens a fresh one
    clear_recent()
    if summary:
        await rag.remember(summary, kind="session")

    return {"ok": True, "summary": summary, "open_hooks": open_hooks,
            "open_quests": open_quests}
