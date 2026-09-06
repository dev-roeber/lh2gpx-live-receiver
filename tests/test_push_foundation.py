from pathlib import Path
import sqlite3

from app.config import Settings


ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "sql" / "push_vapid_v1.sql"


def test_push_foundation_schema_is_explicit_and_empty() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"push_subscriptions", "push_delivery_attempts"} <= tables
    assert connection.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM push_delivery_attempts").fetchone()[0] == 0


def test_web_push_configuration_defaults_to_disabled_without_keys(monkeypatch, tmp_path: Path) -> None:
    for name in ("WEB_PUSH_ENABLED", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings._from_env_base(tmp_path)

    assert settings.web_push_enabled is False
    assert settings.vapid_public_key is None
    assert settings.vapid_private_key_file is None
