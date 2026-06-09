from backend.rules import progression


def _rogue(level=1, con=14, xp=0):
    return {"id": "PC-1", "name": "Kael", "class": "Rogue", "subclass": "Soulknife",
            "level": level, "xp": xp, "max_hp": 10, "hp": 10,
            "abilities": {"str": 12, "dex": 18, "con": con, "int": 11, "wis": 10, "cha": 14},
            "custom_dice": {}, "features": []}


def test_preview_level_2_is_automatic():
    p = progression.preview(_rogue(level=1))
    assert p["new_level"] == 2
    assert p["hp_gain"] == 5 + 2          # rogue d8 avg + CON mod
    assert p["sneak_attack"] == "1d6"
    assert any(f["name"] == "Cunning Action" for f in p["auto_features"])
    assert p["choices"] == []             # no picks at level 2


def test_level_3_grants_soulknife_and_psionics():
    p = progression.preview(_rogue(level=2))
    names = [f["name"] for f in p["auto_features"]]
    assert "Psychic Blades" in names and "Psionic Power" in names
    assert p["psionic"]["die"] == "d6"


def test_level_4_offers_asi_choice_and_applies_feat():
    pc = _rogue(level=3)
    p = progression.preview(pc)
    asi = [c for c in p["choices"] if c["type"] == "asi"]
    assert asi, "level 4 should offer an ASI/feat choice"
    res = progression.apply(pc, {asi[0]["key"]: {"mode": "feat", "feat": "Alert"}})
    assert res["patch"]["level"] == 4
    assert any(f["name"] == "Alert" for f in res["patch"]["features"])


def test_asi_raises_abilities():
    pc = _rogue(level=3)
    key = f"asi_4"
    res = progression.apply(pc, {key: {"mode": "asi", "abilities": {"dex": 1, "con": 1}}})
    assert res["patch"]["abilities"]["con"] == 15  # 14 -> 15


def test_can_level_up_by_xp():
    assert progression.can_level_up(_rogue(level=1, xp=0)) is False
    assert progression.can_level_up(_rogue(level=1, xp=300)) is True  # L2 threshold


def test_generic_class_still_levels():
    pc = {"id": "P", "name": "X", "class": "Bard", "level": 1, "xp": 0, "max_hp": 8, "hp": 8,
          "abilities": {"con": 12}, "custom_dice": {}, "features": []}
    p = progression.preview(pc)
    assert p["new_level"] == 2 and p["hp_gain"] >= 1
    assert p["sneak_attack"] is None
