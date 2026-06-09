from backend.rules import homebrew


def test_ability_mod():
    assert homebrew.ability_mod(10) == 0
    assert homebrew.ability_mod(16) == 3
    assert homebrew.ability_mod(8) == -1


def test_proficiency_bonus():
    assert homebrew.proficiency_bonus(1) == 2
    assert homebrew.proficiency_bonus(5) == 3
    assert homebrew.proficiency_bonus(20) == 6


def test_skill_xp_curve_monotonic():
    xs = [homebrew.skill_xp_for_level(l) for l in (1, 2, 10, 30, 50, 99)]
    assert xs == sorted(xs)
    assert xs[0] == 0


def test_skill_level_roundtrip():
    xp = homebrew.skill_xp_for_level(30)
    assert homebrew.skill_level_for_xp(xp) >= 30
    assert homebrew.skill_level_for_xp(0) == 1


def test_char_level():
    assert homebrew.char_level_for_xp(0) == 1
    assert homebrew.char_level_for_xp(300) >= 2
    assert homebrew.char_level_for_xp(355000) == 20
