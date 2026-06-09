import random

from backend.rules.dice import dc_for, format_result, roll_expression


def test_flat_and_dice():
    random.seed(1)
    r = roll_expression("2d6+3")
    assert len(r.rolls) == 2
    assert all(1 <= x <= 6 for x in r.rolls)
    assert r.total == sum(r.rolls) + 3
    assert r.modifier == 3


def test_ability_modifier_resolution():
    pc = {"abilities": {"str": 16, "dex": 10}, "level": 1}
    r = roll_expression("1d20+STR", pc=pc)
    assert r.modifier == 3  # (16-10)//2


def test_proficiency_token():
    pc = {"abilities": {}, "level": 5, "custom_dice": {}}
    r = roll_expression("1d20+PROF", pc=pc)
    assert r.modifier == 3  # 5e proficiency at level 5


def test_dc_resolution_success_without_dice():
    r = roll_expression("0d20+10", dc=5, label="check")
    assert r.total == 10
    assert r.outcome == "SUCCESS"


def test_format_result_line():
    r = roll_expression("1d20+2", dc=10, label="Athletics")
    line = format_result(r)
    assert line.startswith("ROLL_RESULT: Athletics")
    assert "vs DC 10" in line


def test_difficulty_ladder():
    assert dc_for("easy") == 10
    assert dc_for("hard") == 20
