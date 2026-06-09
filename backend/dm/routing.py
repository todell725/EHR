"""Content-aware model routing.

Lets a campaign use a strong (possibly cloud, possibly content-filtered) model for
general play, while transparently routing mature/romance beats to a local uncensored
model that won't refuse — "if romance then samantha-20b".

Two triggers, belt-and-suspenders:
  * **proactive** — keyword heuristic on the action + current scene picks the model
    before generating;
  * **reactive** — if the primary model returns something that looks like a refusal,
    the orchestrator regenerates on the intimate model.
"""

from __future__ import annotations

import re

from backend.core.config import settings

# EXPLICIT signals only. Proactive routing to the uncensored model should fire ONLY for
# content a normal model would actually refuse — NOT for tame romance (kisses, confessions,
# longing), which the main model narrates better. Anything in between is caught reactively
# (if the main model refuses, we regenerate on the intimate model).
_INTIMATE = {
    "naked", "nude", "undress", "undressing", "undressed", "arousal", "aroused", "orgasm",
    "climax", "thrust", "thrusting", "moan", "moaning", "nipple", "nipples", "breasts",
    "genitals", "penetrate", "penetration", "horny", "erotic", "erotica", "sex", "sexual",
    "lovemaking", "make love", "making love", "consummate", "consummating", "in bed together",
    "bodies entwined", "between her thighs", "between his thighs",
}
_WORD = re.compile(r"[a-z']+")

_REFUSAL_MARKERS = (
    "i can't", "i cannot", "i can not", "i'm not able", "i am not able", "i'm unable",
    "i am unable", "i won't be able", "i must decline", "i'm sorry, but", "i am sorry, but",
    "as an ai", "i'm not comfortable", "not able to continue", "against my guidelines",
    "i won't write", "i will not write", "i'm not going to",
)


def is_intimate(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    if "make love" in blob:
        return True
    toks = set(_WORD.findall(blob))
    return bool(toks & _INTIMATE)


def looks_like_refusal(text: str) -> bool:
    head = (text or "").strip()[:300].lower()
    if any(m in head for m in _REFUSAL_MARKERS):
        return True
    # very short + apologetic is also a refusal tell
    return len(text.strip()) < 140 and ("sorry" in head or "can't" in head)


def pick_narration_model(action: str, scene: str = "") -> tuple[str, bool]:
    """Return (model, is_intimate_route). Falls back to the default narration model."""
    if (
        settings.route_intimate
        and settings.intimate_model
        and is_intimate(action, scene)
    ):
        return settings.intimate_model, True
    return settings.narration_model, False
