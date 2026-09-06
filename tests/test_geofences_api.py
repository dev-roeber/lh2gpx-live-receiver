import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(tmp_path: Path, *, enabled: bool = False) -> TestClient:
    data = tmp_path / "data"
    settings = Settings(
        bind_host="127.0.0.1", port=8080, public_hostname="localhost", public_base_url="http://localhost:8080",
        bearer_token=None, data_dir=data, sqlite_path=data / "receiver.sqlite3",
        raw_payload_ndjson_path=data / "raw.ndjson", legacy_request_ndjson_path=data / "legacy.ndjson",
        raw_payload_ndjson_enabled=True, local_timezone="UTC", log_level="INFO", request_body_max_bytes=262144,
        points_page_size_default=50, points_page_size_max=250, rate_limit_requests_per_minute=0,
        trust_proxy_headers=True, geofencing_enabled=enabled,
    )
    return TestClient(create_app(settings))


BODY = {
    "geofence_id": "home",
    "name": "Home",
    "center_latitude": 52.52,
    "center_longitude": 13.405,
    "radius_m": 100,
    "hysteresis_m": 25,
}


def test_disabled_flag_does_not_expose_or_process_geofences(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    response = test_client.get("/api/geofences")
    assert response.status_code == 404
    with sqlite3.connect(test_client.app.state.storage.sqlite_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "geofences" in tables  # Foundation schema is separate from runtime evaluation.
    assert connection.execute("SELECT COUNT(*) FROM geofences").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM geofence_subject_state").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM geofence_transitions").fetchone()[0] == 0


def test_admin_api_manages_disabled_by_default_circle_geofences(tmp_path: Path) -> None:
    test_client = client(tmp_path, enabled=True)
    created = test_client.post("/api/geofences", json=BODY)
    assert created.status_code == 201
    assert created.json()["geofence"]["enabled"] is False
    assert test_client.get("/api/geofences").json()["geofences"][0]["hysteresisM"] == 25
    updated = test_client.patch("/api/geofences/home", json={"enabled": True, "name": "Home zone"})
    assert updated.status_code == 200
    assert updated.json()["geofence"]["enabled"] is True
    deleted = test_client.delete("/api/geofences/home")
    assert deleted.status_code == 200
    assert test_client.get("/api/geofences").json()["geofences"] == []


def test_live_location_enter_transition_is_visible_via_transitions_endpoint(tmp_path: Path) -> None:
    test_client = client(tmp_path, enabled=True)
    created = test_client.post("/api/geofences", json=BODY)
    assert created.status_code == 201
    enabled = test_client.patch("/api/geofences/home", json={"enabled": True})
    assert enabled.status_code == 200

    payload = {
        "source": "LocationHistory2GPX-iOS",
        "sessionID": "123e4567-e89b-12d3-a456-426614174000",
        "captureMode": "foregroundWhileInUse",
        "sentAt": "2026-09-06T12:00:10Z",
        "points": [
            {
                "latitude": 52.52,
                "longitude": 13.405,
                "timestamp": "2026-09-06T12:00:00Z",
                "horizontalAccuracyM": 5.0,
            }
        ],
    }
    ingest = test_client.post("/live-location", json=payload)
    assert ingest.status_code == 202

    transitions = test_client.get("/api/geofences/home/transitions")
    assert transitions.status_code == 200
    body = transitions.json()
    assert body["geofenceId"] == "home"
    assert len(body["transitions"]) == 1
    entry = body["transitions"][0]
    assert entry["transition"] == "enter"
    assert entry["pointTimestampUtc"] == "2026-09-06T12:00:00Z"
    assert entry["latitude"] == 52.52
    assert entry["longitude"] == 13.405

    with sqlite3.connect(test_client.app.state.storage.sqlite_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM geofence_transitions WHERE geofence_id = 'home' AND transition = 'enter'"
        ).fetchone()[0] == 1


def test_transitions_endpoint_requires_enabled_flag_and_valid_geofence(tmp_path: Path) -> None:
    test_client = client(tmp_path, enabled=True)
    test_client.post("/api/geofences", json=BODY)
    missing = test_client.get("/api/geofences/does-not-exist/transitions")
    assert missing.status_code == 404

    disabled_client = client(tmp_path)
    disabled = disabled_client.get("/api/geofences/home/transitions")
    assert disabled.status_code == 404


def test_only_circle_geofences_are_exposed_and_validation_is_server_side(tmp_path: Path) -> None:
    test_client = client(tmp_path, enabled=True)
    invalid = dict(BODY, center_latitude=91)
    assert test_client.post("/api/geofences", json=invalid).status_code == 422
    test_client.app.state.storage.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(test_client.app.state.storage.sqlite_path)
    connection.executescript(Path(__file__).parents[1].joinpath("sql/geofencing_v1.sql").read_text())
    connection.execute("INSERT INTO geofences (geofence_id,name,geometry_type,polygon_geojson,created_at_utc,updated_at_utc) VALUES ('poly','Poly','polygon','{}','now','now')")
    connection.commit(); connection.close()
    assert [item["geofenceId"] for item in test_client.get("/api/geofences").json()["geofences"]] == []
