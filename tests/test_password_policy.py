from password_policy import PasswordPolicy as P


def test_rejects_too_short():
    ok, _ = P.validate("Ab1!xy", "user")
    assert ok is False


def test_requires_uppercase():
    assert P.validate("abc123!xyzqw", "user")[0] is False


def test_rejects_common_password():
    assert P.validate("Password123!xx", "user")[0] is False


def test_rejects_username_inside_password():
    assert P.validate("Alice!Str0ngPw", "alice")[0] is False


def test_rejects_sequential_characters():
    assert P.validate("Abcdef123456!", "user")[0] is False


def test_accepts_strong_password():
    ok, msg = P.validate("K9x!mQ7wLp2z", "user")
    assert ok is True and msg == "OK"


def test_strength_score_rewards_stronger_passwords():
    weak = P.get_strength_score("aaaa")[0]
    strong = P.get_strength_score("K9x!mQ7wLp2z")[0]
    assert strong > weak
