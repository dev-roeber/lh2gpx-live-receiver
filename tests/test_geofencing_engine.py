import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.geofencing import CircleGeofence, GeofenceEngine, GeofencePoint

SCHEMA = Path(__file__).parents[1] / "sql" / "geofencing_v1.sql"


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    db.execute(
        """INSERT INTO geofences
           (geofence_id, name, geometry_type, enabled, center_latitude,
            center_longitude, radius_m, hysteresis_m, created_at_utc, updated_at_utc)
           VALUES ('home', 'Home', 'circle', 1, 52.5200, 13.4050, 100, 50, 'now', 'now')"""
    )
    return db


def point(key: str, latitude: float, *, minute: int) -> GeofencePoint:
    return GeofencePoint("phone", "receiver", key, datetime(2026, 9, 6, 12, minute, tzinfo=timezone.utc), latitude, 13.4050)


def test_disabled_by_default_and_historical_points_are_ignored() -> None:
    db = connection()
    engine = GeofenceEngine(db)
    assert engine.evaluate_point(point("old", 52.5200, minute=0), historical=True) == []
    assert db.execute("SELECT COUNT(*) FROM geofence_subject_state").fetchone()[0] == 0


def test_hysteresis_emits_enter_and_exit_only_after_outer_boundary() -> None:
    db = connection()
    engine = GeofenceEngine(db, enabled=True)
    assert engine.evaluate_point(point("p1", 52.5200, minute=0))[0].transition == "enter"
    # About 111 m north: outside the 100 m entry radius but inside the 150 m exit radius.
    assert engine.evaluate_point(point("p2", 52.5210, minute=1)) == []
    # About 222 m north: outside the hysteresis-expanded exit radius.
    assert engine.evaluate_point(point("p3", 52.5220, minute=2))[0].transition == "exit"


def test_reprocessing_same_point_is_idempotent() -> None:
    db = connection()
    engine = GeofenceEngine(db, enabled=True)
    first = engine.evaluate_point(point("same", 52.5200, minute=0))
    second = engine.evaluate_point(point("same", 52.5200, minute=0))
    assert len(first) == 1
    assert second == []
    assert db.execute("SELECT COUNT(*) FROM geofence_transitions").fetchone()[0] == 1


def test_disabled_geofence_is_not_processed() -> None:
    db = connection()
    db.execute("UPDATE geofences SET enabled = 0")
    engine = GeofenceEngine(db, enabled=True)
    assert engine.evaluate_point(point("p1", 52.5200, minute=0)) == []
    assert db.execute("SELECT COUNT(*) FROM geofence_subject_state").fetchone()[0] == 0
