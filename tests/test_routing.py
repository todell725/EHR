from backend.dm import routing


def test_is_intimate():
    # explicit content routes to the uncensored model
    assert routing.is_intimate("we finally make love")
    assert routing.is_intimate("she pulls me into the bedroll, naked")
    # tame romance does NOT — the main model handles it better
    assert not routing.is_intimate("I kiss her softly and confess my feelings")
    assert not routing.is_intimate("I'd gladly give my lifesblood for you")
    assert not routing.is_intimate("I swing my sword at the goblin")


def test_refusal_detection():
    assert routing.looks_like_refusal("I can't continue this scene.")
    assert routing.looks_like_refusal("I'm sorry, but I won't write that.")
    assert not routing.looks_like_refusal(
        "You step into the cold hall and draw your blade, shadows shifting on the walls."
    )


def test_pick_model_routes_intimate(monkeypatch):
    monkeypatch.setattr(routing.settings, "route_intimate", True)
    monkeypatch.setattr(routing.settings, "intimate_model", "samantha")
    monkeypatch.setattr(routing.settings, "narration_model", "kimi")
    m, intimate = routing.pick_narration_model("we make love by the fire")
    assert m == "samantha" and intimate is True
    m2, i2 = routing.pick_narration_model("I attack the wolf")
    assert m2 == "kimi" and i2 is False


def test_pick_model_off_by_default(monkeypatch):
    monkeypatch.setattr(routing.settings, "route_intimate", False)
    monkeypatch.setattr(routing.settings, "intimate_model", "samantha")
    m, intimate = routing.pick_narration_model("we make love")
    assert intimate is False
