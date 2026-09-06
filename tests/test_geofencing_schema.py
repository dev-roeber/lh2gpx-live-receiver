from pathlib import Path
import sqlite3


SCHEMA = Path(__file__).parents[1] / "sql" / "geofencing_v1.sql"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    return connection


def test_geofencing_schema_is_disabled_and_has_no_push_tables() -> None:
    connection = _connection()
    connection.execute(
        """
        INSERT INTO geofences (
            geofence_id, name, geometry_type, center_latitude,
            center_longitude, radius_m, created_at_utc, updated_at_utc
        ) VALUES ('home', 'Home', 'circle', 52.5, 13.4, 100,
                  '2026-09-06T00:00:00Z', '2026-09-06T00:00:00Z')
        """
    )
    enabled = connection.execute(
        "SELECT enabled FROM geofences WHERE geofence_id = 'home'"
    ).fetchone()[0]
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert enabled == 0
    assert "push_subscriptions" not in tables
    assert "notification_queue" not in tables


def test_geofencing_schema_rejects_invalid_geometry_and_coordinates() -> None:
    connection = _connection()
    for values in (
        ("bad-range", 95.0, 13.4, 100),
        ("bad-radius", 52.5, 13.4, 0),
    ):
        try:
            connection.execute(
                """
                INSERT INTO geofences (
                    geofence_id, name, geometry_type, center_latitude,
                    center_longitude, radius_m, created_at_utc, updated_at_utc
                ) VALUES (?, 'invalid', 'circle', ?, ?, ?, 'now', 'now')
                """,
                values,
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("invalid geofence geometry was accepted")
