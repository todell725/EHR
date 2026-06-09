"""Private 1-on-1 companion chat — out of campaign, in character.

A quiet side-channel: you talk directly to a party companion (no DM narrator, no
mechanics, no dice). The companion answers in first person, grounded in who they are
(their NPC origin's personality/wants/fears + disposition toward the hero) and lightly
aware of recent events. Runs on the cheap local CHAT_MODEL (gemma) — prose polish isn't
the point here, responsiveness is.

Deliberately 1-on-1, not a group chat: one clear voice, no who-speaks-next coordination.
"""

from __future__ import annotations

import re

from backend.core import db, state
from backend.core.config import settings
from backend.dm import routing
from backend.llm.client import get_llm


def history(character_id: str, limit: int = 40) -> list[dict]:
    rows = db.query(
        "SELECT role, content FROM companion_chats WHERE character_id = ? "
        "ORDER BY id DESC LIMIT ?",
        [character_id, limit],
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _save(character_id: str, role: str, content: str) -> None:
    db.execute(
        "INSERT INTO companion_chats (character_id, role, content) VALUES (?,?,?)",
        [character_id, role, content],
    )


def clear(character_id: str) -> None:
    db.execute("DELETE FROM companion_chats WHERE character_id = ?", [character_id])


def _disposition_word(n: int | None) -> str:
    if n is None:
        return "still taking your measure"
    if n <= -25:
        return "hostile and guarded toward"
    if n < 0:
        return "wary of"
    if n < 20:
        return "warming to"
    if n < 50:
        return "fond of and loyal to"
    return "devoted to"


def _system_prompt(pc: dict, npc: dict | None, hero_name: str) -> str:
    n = npc or {}
    traits = ", ".join(n.get("personality") or []) or "your own quiet ways"
    disp = _disposition_word((n.get("disposition") or {}).get(_hero_id()))
    bits = [
        f"You are {pc['name']}"
        + (f", {n['pronouns']}" if n.get("pronouns") else "")
        + f", a {pc.get('race','')} {pc.get('class','')} traveling with {hero_name}.",
        f"Personality: {traits}.",
    ]
    if n.get("want"):
        bits.append(f"You want: {n['want']}.")
    if n.get("fear"):
        bits.append(f"You fear: {n['fear']}.")
    if n.get("secret"):
        bits.append(f"A secret you guard (do not blurt it out): {n['secret']}.")
    bits.append(f"You are {disp} {hero_name}.")

    beats = state.recent_chronicle(limit=5)
    if beats:
        bits.append("Recent things you've lived through together: "
                    + " ".join(b["content"] for b in beats))

    bits.append(
        f"This is a private, off-the-record moment between you and {hero_name} — NOT the "
        f"main adventure. There is no narrator. Speak ONLY as {pc['name']}, first person, "
        f"casual and human. Keep replies short (1-4 sentences) unless asked for more. React "
        f"honestly given your bond; stay in character.")
    return "\n".join(bits)


def _hero_id() -> str:
    h = state.heroes()
    return h[0]["id"] if h else ""


def current_disposition(character_id: str) -> int | None:
    """The companion's current regard for the hero (from their origin NPC record)."""
    pc = state.get_pc(character_id)
    npc = state.find_npc_by_name(pc["name"]) if pc else None
    if not npc:
        return None
    return int((npc.get("disposition") or {}).get(_hero_id(), 0))


async def _judge_exchange(user_text: str, reply: str, name: str, hero: str) -> int:
    """Cheap relationship read: how did this exchange shift the companion's regard?
    Returns a small integer in [-2, 2] so bonds build gradually over many chats."""
    try:
        out = await get_llm().chat(
            [
                {"role": "system", "content":
                    f"You judge how {name}'s feelings toward {hero} shifted after ONE exchange. "
                    f"Reply with ONLY an integer from -2 (hurt or angered) to +2 (touched, drawn "
                    f"closer); 0 if neutral small talk."},
                {"role": "user", "content":
                    f"{hero} said: {user_text}\n{name} replied: {reply}\nShift (just the number):"},
            ],
            mode="adjudication", model=settings.chat_model, temperature=0.1,
        )
        m = re.search(r"-?\d+", out or "")
        return max(-2, min(2, int(m.group()))) if m else 0
    except Exception:  # noqa: BLE001 - relationship nudge is best-effort
        return 0


async def send(character_id: str, text: str) -> dict | None:
    pc = state.get_pc(character_id)
    if pc is None:
        return None
    hero = state.heroes()
    hero_name = hero[0]["name"] if hero else "the hero"
    hero_id = hero[0]["id"] if hero else ""
    npc = state.find_npc_by_name(pc["name"])  # origin NPC carries personality/disposition

    messages = (
        [{"role": "system", "content": _system_prompt(pc, npc, hero_name)}]
        + history(character_id)
        + [{"role": "user", "content": text}]
    )
    # use the SAME model the DM game uses — the narration model, with the same intimate
    # routing (so a romantic 1-on-1 reads as well as the campaign, not the cheap chat model)
    model, _ = routing.pick_narration_model(text)
    reply = await get_llm().chat(messages, model=model, temperature=0.85)
    reply = (reply or "").strip()
    _save(character_id, "user", text)
    _save(character_id, "assistant", reply)

    # relationship nudge — talking to a companion actually builds the bond
    delta, disposition = 0, None
    if npc and hero_id:
        delta = await _judge_exchange(text, reply, pc["name"], hero_name)
        disposition = (state.set_npc_disposition(npc["id"], hero_id, delta) if delta
                       else int((npc.get("disposition") or {}).get(hero_id, 0)))
    return {"reply": reply, "delta": delta, "disposition": disposition}
