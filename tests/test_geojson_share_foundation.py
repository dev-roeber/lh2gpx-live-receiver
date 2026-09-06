from pathlib import Path
import sqlite3

from app.config import Settings
from app.geojson_share_foundation import (
    FAILED_ATTEMPT_LIMIT,
    FailedShareAttemptLimiter,
    hash_share_token,
    new_share_token,
    share_is_active,
)


ROOT = Path(__file__).parents[1]


def test_share_token_is_opaque_and_only_hash_is_persistable() -> None:
    token = new_share_token()

    assert len(token) >= 40
    assert token != hash_share_token(token)
    assert hash_share_token(token) == hash_share_token(token)
    assert hash_share_token(token) != hash_share_token(new_share_token())


def test_share_lifecycle_requires_unrevoked_and_unexpired_record() -> None:
    assert share_is_active(expires_at=100, now=99)
    assert not share_is_active(expires_at=100, now=100)
    assert not share_is_active(expires_at=100, revoked_at=90, now=99)


def test_failed_share_attempt_limiter_blocks_after_limit_and_expires() -> None:
    limiter = FailedShareAttemptLimiter(limit=FAILED_ATTEMPT_LIMIT, window_seconds=60)

    for index in range(FAILED_ATTEMPT_LIMIT):
        assert limiter.allow("client", now=float(index))
        limiter.record_failure("client", now=float(index))
    assert not limiter.allow("client", now=FAILED_ATTEMPT_LIMIT)
    assert limiter.allow("client", now=61)


def test_share_schema_is_explicit_and_empty() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript((ROOT / "sql/geojson_share_v1.sql").read_text(encoding="utf-8"))

    assert connection.execute("SELECT COUNT(*) FROM geojson_shares").fetchone()[0] == 0


def test_geojson_sharing_defaults_to_disabled_and_is_not_a_route_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEOJSON_SHARING_ENABLED", raising=False)
    settings = Settings._from_env_base(tmp_path)

    assert settings.geojson_sharing_enabled is False
