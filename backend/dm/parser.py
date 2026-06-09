"""Parse the DM's four-section output into a structured `ParsedTurn`.

Contract (see `dm/prompt.py`): every response contains, in order,
`[NARRATIVE]`, `[MECHANICS]`, `[SUGGESTIONS]`, `[CHRONICLE]`. Narration bleeding into
the mechanics block corrupts state, so we parse defensively and surface `parse_ok`
so the orchestrator can retry once.
"""

from __future__ import annotations

import json
import re

from backend.core.models import Mechanic, ParsedTurn, Suggestion

# Tolerant header matcher: optional markdown bold, brackets, any case.
_HEADER = re.compile(
    r"^\s*\**\s*\[?\s*(NARRATIVE|MECHANICS|SUGGESTIONS|CHRONICLE)\s*\]?\s*\**\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# A mechanics directive: UPPER_SNAKE tag, then `:` then comma args.
_MECH = re.compile(r"^\s*[-*]?\s*([A-Z][A-Z0-9_]{2,}):\s*(.*)$")
_SUGG_NUM = re.compile(r"^\s*(?:\d+[.)]|[-*])\s*(.+)$")
_ROLL_FLAG = re.compile(r"requires\s+roll\s*:?\s*(yes|no)", re.IGNORECASE)


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(_HEADER.finditer(text))
    if not matches:
        # No headers at all: treat the whole thing as narrative.
        return {"narrative": text.strip()}
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _parse_mechanics(block: str) -> tuple[list[Mechanic], list[str]]:
    mechs, notes = [], []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MECH.match(line)
        if not m:
            if line.lower() not in ("none", "n/a", "-"):
                notes.append(f"unparsed mechanics line: {line!r}")
            continue
        tag = m.group(1).upper()
        args = [a.strip() for a in m.group(2).split(",") if a.strip()]
        mechs.append(Mechanic(tag=tag, args=args, raw=line))
    return mechs, notes


def _parse_suggestions(block: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SUGG_NUM.match(line)
        body = m.group(1) if m else line
        requires_roll = False
        roll_hint = None
        flag = _ROLL_FLAG.search(body)
        if flag:
            requires_roll = flag.group(1).lower() == "yes"
            # text before the parenthetical is the option; hint is after the dash
            paren = re.search(r"\(([^)]*)\)", body)
            if paren:
                inner = paren.group(1)
                body = body[: body.index("(")].strip(" -–—")
                dash = re.split(r"[-–—]", inner, maxsplit=1)
                if len(dash) == 2:
                    roll_hint = dash[1].strip()
        out.append(Suggestion(text=body.strip(), requires_roll=requires_roll, roll_hint=roll_hint))
    return out[:5]


def parse_json(text: str) -> ParsedTurn:
    """Parse a strict-mode JSON object response into a ParsedTurn.

    Tolerant of fenced/extra text (extracts the first balanced object) and of
    mechanics/suggestions given as either objects or plain strings.
    """
    raw = text.strip()
    start, depth, blob = raw.find("{"), 0, None
    if start != -1:
        for i in range(start, len(raw)):
            depth += raw[i] == "{"
            depth -= raw[i] == "}"
            if depth == 0:
                blob = raw[start : i + 1]
                break
    try:
        data = json.loads(blob if blob else raw)
    except (TypeError, json.JSONDecodeError):
        return ParsedTurn(parse_ok=False, parse_notes=["JSON parse failed"])

    mechs: list[Mechanic] = []
    for m in data.get("mechanics", []) or []:
        if isinstance(m, str):
            parsed, _ = _parse_mechanics(m)
            mechs.extend(parsed)
        elif isinstance(m, dict) and m.get("tag"):
            args = m.get("args", [])
            args = [str(a) for a in (args if isinstance(args, list) else [args])]
            mechs.append(Mechanic(tag=str(m["tag"]).upper(), args=args,
                                  raw=f"{m['tag']}: {', '.join(args)}"))

    suggs: list[Suggestion] = []
    for s in data.get("suggestions", []) or []:
        if isinstance(s, str):
            suggs.extend(_parse_suggestions(s))
        elif isinstance(s, dict):
            suggs.append(Suggestion(text=str(s.get("text", "")),
                                    requires_roll=bool(s.get("requires_roll", False)),
                                    roll_hint=s.get("roll_hint")))

    chronicle = (data.get("chronicle") or "").strip() or None
    if chronicle and chronicle.lower() in ("none", "n/a", "omit", "-"):
        chronicle = None

    narrative = (data.get("narrative") or "").strip()
    return ParsedTurn(
        narrative=narrative, mechanics=mechs, suggestions=suggs[:5],
        chronicle=chronicle, parse_ok=bool(narrative),
        parse_notes=[] if narrative else ["missing narrative in JSON"],
    )


_STREAM_HOLDBACK = 12  # withhold a tail so a forming "[MECH..." header never leaks


def streaming_narrative(full: str) -> tuple[str, bool]:
    """Display-safe narrative for live streaming.

    Returns `(text_so_far, closed)`. Strips the leading `[NARRATIVE]` header, stops at
    the next section header (`closed=True`), and while still open withholds a short tail
    so a partially-streamed header isn't shown mid-flight. The prefix is stable across
    calls, so callers can emit only the newly-grown suffix.
    """
    matches = list(_HEADER.finditer(full))
    nar = next((m for m in matches if m.group(1).lower() == "narrative"), None)

    if nar is None:
        stripped = full.lstrip()
        if stripped.startswith("[") and len(stripped) < 25:
            return "", False  # a header is probably forming; wait
        start, nxt = 0, None
    else:
        start = nar.end()
        while start < len(full) and full[start] in " \t\r\n":
            start += 1
        nxt = next((m for m in matches if m.start() >= start), None)

    end = nxt.start() if nxt else len(full)
    text = full[start:end]
    closed = nxt is not None
    if not closed:
        text = text[:-_STREAM_HOLDBACK] if len(text) > _STREAM_HOLDBACK else ""
    return (text.rstrip() if closed else text), closed


def parse(text: str) -> ParsedTurn:
    sections = _split_sections(text or "")
    narrative = sections.get("narrative", "").strip()

    mechs, notes = _parse_mechanics(sections.get("mechanics", ""))
    suggestions = _parse_suggestions(sections.get("suggestions", ""))

    chronicle = sections.get("chronicle", "").strip() or None
    if chronicle and chronicle.lower() in ("none", "n/a", "omit", "-"):
        chronicle = None

    parse_ok = bool(narrative)
    if not parse_ok:
        notes.append("missing or empty [NARRATIVE] section")

    return ParsedTurn(
        narrative=narrative,
        mechanics=mechs,
        suggestions=suggestions,
        chronicle=chronicle,
        parse_ok=parse_ok,
        parse_notes=notes,
    )
