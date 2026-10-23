"""Guest passwords and the host PIN: salted scrypt hashes, plus a brake against guessing.

Why scrypt: it is in Python's standard library (no new dependency) and is deliberately slow
and memory-hungry, so a stolen party.db can't be turned back into passwords quickly. Every
hash has its own random salt, so two guests with the same password get different hashes.
Hashing takes ~50 ms: routers call these through asyncio.to_thread.

The PIN is short (4+ digits), so wrong guesses are rate-limited: 5 failures in a row lock
that key (device + what is being guessed) for a minute. Kept in memory: a restart clears it.
"""
import hashlib
import hmac
import secrets
import time

_N, _R, _P = 2**14, 8, 1          # scrypt cost: ~16 MB memory, ~50 ms on a laptop


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${salt.hex()}${digest.hex()}"


def verify(secret: str, stored: str | None) -> bool:
    """Constant-time comparison, so response times don't leak how close a guess was."""
    try:
        _, n, salt, digest = (stored or "").split("$")
        check = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(salt), n=int(n), r=_R, p=_P, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check.hex(), digest)


class Brake:
    """`limit` failures in a row -> locked for `lock_seconds`; a success forgives them."""

    def __init__(self, limit: int = 5, lock_seconds: float = 60) -> None:
        self.limit, self.lock_seconds = limit, lock_seconds
        self._fails: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def wait_seconds(self, key: str) -> int:
        """0 = may try now; otherwise how long this key is still locked."""
        left = self._locked_until.get(key, 0) - time.monotonic()
        if left <= 0 and key in self._locked_until:   # lock over: a fresh set of tries
            self._locked_until.pop(key)
            self._fails.pop(key, None)
        return max(0, int(left + 0.999))

    def failed(self, key: str) -> None:
        self._fails[key] = self._fails.get(key, 0) + 1
        if self._fails[key] >= self.limit:
            self._locked_until[key] = time.monotonic() + self.lock_seconds

    def succeeded(self, key: str) -> None:
        self._fails.pop(key, None)
        self._locked_until.pop(key, None)


brake = Brake()
