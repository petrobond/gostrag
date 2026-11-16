"""Login throttling backed by PostgreSQL (survives restarts, no extra infra)."""

from __future__ import annotations

from app.web.security import token_hash


class LoginThrottle:
    def __init__(self, ip_limit: int, email_limit: int, window_min: int) -> None:
        self.ip_limit = max(1, ip_limit)
        self.email_limit = max(1, email_limit)
        self.window_sec = max(1, window_min) * 60

    @staticmethod
    def _ip_key(ip: str) -> str:
        return f"ip:{ip}"

    @staticmethod
    def _email_key(email: str) -> str:
        return f"email:{token_hash(email)}"

    async def check(self, store, ip: str, email: str) -> bool:
        if ip and await store.count_login_attempts(self._ip_key(ip), self.window_sec) >= self.ip_limit:
            return False
        if not email:
            return True
        email_attempts = await store.count_login_attempts(self._email_key(email), self.window_sec)
        return email_attempts < self.email_limit

    async def fail(self, store, ip: str, email: str) -> None:
        if ip:
            await store.record_login_attempt(self._ip_key(ip))
        if email:
            await store.record_login_attempt(self._email_key(email))

    async def reset(self, store, email: str) -> None:
        if email:
            await store.clear_login_attempts(self._email_key(email))
