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
