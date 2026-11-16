"""Password hashing, tokens and input validation for the web UI."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Unknown emails still run a verification to keep response time flat.
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(16))

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+){1,4}$")
MAX_PASSWORD_LEN = 128


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> tuple[bool, bool]:
    """Return (verified, needs_rehash)."""
    try:
        verified = PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return verified, PASSWORD_HASHER.check_needs_rehash(password_hash)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    return len(value) <= 254 and bool(EMAIL_RE.match(value))


def password_problem(password: str, min_len: int) -> str | None:
    if len(password) < min_len:
        return f"Пароль должен быть не короче {min_len} символов."
    if len(password) > MAX_PASSWORD_LEN:
        return f"Пароль слишком длинный (максимум {MAX_PASSWORD_LEN} символов)."
    if password.isdigit():
        return "Пароль не должен состоять только из цифр."
    if not any(char.isalpha() for char in password):
        return "Пароль должен содержать хотя бы одну букву."
    return None
