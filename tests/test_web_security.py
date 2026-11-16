from app.web.security import (
    constant_time_equals,
    hash_password,
    is_valid_email,
    new_token,
    normalize_email,
    password_problem,
    token_hash,
    verify_password,
)


def test_password_hash_roundtrip_and_rehash_flag():
    digest = hash_password("correct horse battery")
    assert digest.startswith("$argon2id$")
    assert verify_password(digest, "correct horse battery") == (True, False)
    assert verify_password(digest, "wrong password") == (False, False)
    assert verify_password("not-a-hash", "correct horse battery") == (False, False)


def test_token_hash_is_stable_and_hides_token():
    token = new_token()
    assert token != token_hash(token)
    assert len(token_hash(token)) == 64
    assert token_hash(token) == token_hash(token)


def test_constant_time_equals():
    assert constant_time_equals("same-value", "same-value")
    assert not constant_time_equals("same-value", "other-value")


def test_email_validation_and_normalization():
    assert normalize_email(" User@Example.RU ") == "user@example.ru"
    assert is_valid_email("user@example.ru")
    assert not is_valid_email("user@")
    assert not is_valid_email("no-at-sign")


def test_password_policy():
    assert password_problem("short", 12) is not None
    assert password_problem("123456789012", 12) is not None
    assert password_problem("correct horse battery", 12) is None
