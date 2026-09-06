"""Route-free primitives for the future GeoJSON share-link feature.

This module deliberately does not create links, access the database, register
routes, or serve files. It only centralizes the security rules that future
route code must use and makes them independently testable.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque

TOKEN_BYTES = 32
SHARE_TTL_SECONDS = 24 * 60 * 60
MAX_DOWNLOADS = 10
FAILED_ATTEMPT_LIMIT = 10
FAILED_ATTEMPT_WINDOW_SECONDS = 15 * 60


def new_share_token() -> str:
    """Return a high-entropy opaque token for a future share link."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_share_token(token: str) -> str:
    """Return the only token representation suitable for persistence."""
    if not isinstance(token, str) or not token:
        raise ValueError("share token must not be empty")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def share_is_active(*, expires_at: float, revoked_at: float | None = None, now: float | None = None) -> bool:
    """Check expiry/revocation without extending the share lifetime."""
    current = time.time() if now is None else float(now)
    return revoked_at is None and current < float(expires_at)


class FailedShareAttemptLimiter:
    """Small process-local limiter for invalid share-token attempts.

    It is only a foundation. A future public route must decide whether a
    process-local limiter is sufficient or use a shared durable limiter.
    """

    def __init__(self, *, limit: int = FAILED_ATTEMPT_LIMIT, window_seconds: int = FAILED_ATTEMPT_WINDOW_SECONDS) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate-limit values must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._failures: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else float(now)
        bucket = self._failures[key]
        cutoff = current - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return len(bucket) < self.limit

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        if self.allow(key, now=current):
            self._failures[key].append(current)

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)
