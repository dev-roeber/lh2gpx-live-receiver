from __future__ import annotations

import base64
import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.import_parsers import parse_file_report
from app.main import create_app
from app.storage import StorageWriteError


def test_health_endpoint_returns_service_status(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "lh2gpx-live-receiver"
    assert body["authRequired"] is False
    assert body["storageReady"] is True
    assert body["sqlitePath"].endswith("receiver.sqlite3")


def test_readyz_reports_storage_not_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.app.state.storage._ready = False
    client.app.state.storage._last_error = "permission denied"

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_auth_required_rejects_missing_bearer_token(tmp_path: Path) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 401
    assert response.json()["error"]["detail"] == "Missing or invalid bearer token."


def test_invalid_token_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    response = client.post(
        "/live-location",
        json=valid_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_valid_token_accepts_payload_and_persists_points(tmp_path: Path) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    response = client.post(
        "/live-location",
        json=valid_payload(),
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["pointsAccepted"] == 2
    assert body["storage"]["sqlitePath"].endswith("receiver.sqlite3")
    assert query_scalar(tmp_path, "SELECT COUNT(*) FROM gps_points") == 2
    assert query_scalar(tmp_path, "SELECT COUNT(*) FROM ingest_requests WHERE ingest_status = 'accepted'") == 1
    assert read_raw_payload_file(tmp_path)[0]["payload"]["extraTopLevel"] == {"device": "iPhone 15 Pro Max"}


def test_unknown_additive_fields_remain_compatible(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 202
    stored_payload = query_text(
        tmp_path,
        "SELECT raw_payload_json FROM ingest_requests ORDER BY received_at_utc DESC LIMIT 1",
    )
    parsed = json.loads(stored_payload)
    assert parsed["extraTopLevel"] == {"device": "iPhone 15 Pro Max"}
    assert parsed["points"][0]["extraPointField"] == "kept"


def test_invalid_payload_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    payload = valid_payload()
    payload["points"][0]["latitude"] = 181

    response = client.post("/live-location", json=payload)

    assert response.status_code == 422
    assert query_scalar(tmp_path, "SELECT COUNT(*) FROM gps_points") == 0


def test_storage_error_returns_503_and_is_recorded(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    def fail_ingest(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise StorageWriteError("disk full")

    client.app.state.storage.ingest_success = fail_ingest
    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["category"] == "storage_write_failed"
    assert body["requestId"]


def test_unexpected_error_returns_500_with_request_id(tmp_path: Path) -> None:
    client = make_client(tmp_path, raise_server_exceptions=False)

    def explode(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    client.app.state.storage.ingest_success = explode
    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 500
    body = response.json()
    assert body["requestId"]
    assert body["error"]["category"] == "unexpected_internal_error"


def test_points_endpoints_filter_and_export(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    client.post("/live-location", json=valid_payload())

    headers = basic_auth_headers("operator", "dashboard-pass")
    response = client.get(
        "/api/points?date_from=2026-03-20&date_to=2026-03-20&time_from=11:59:59&time_to=12:00:10&session_id=123e4567-e89b-12d3-a456-426614174000",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["points"]["total"] == 2
    assert body["points"]["items"][0]["session_id"] == "123e4567-e89b-12d3-a456-426614174000"

    csv_response = client.get("/api/points?format=csv", headers=headers)
    assert csv_response.status_code == 200
    assert "point_timestamp_utc" in csv_response.text

    ndjson_response = client.get("/api/points?format=ndjson", headers=headers)
    assert ndjson_response.status_code == 200
    assert ndjson_response.text.count("\n") >= 1


def test_request_and_session_detail_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    client.post("/live-location", json=valid_payload())
    headers = basic_auth_headers("operator", "dashboard-pass")

    requests_response = client.get("/api/requests", headers=headers)
    request_id = requests_response.json()["requests"]["items"][0]["request_id"]
    detail_response = client.get(f"/api/requests/{request_id}", headers=headers)
    session_response = client.get("/api/sessions", headers=headers)
    session_id = session_response.json()["sessions"][0]["session_id"]
    session_detail = client.get(f"/api/sessions/{session_id}", headers=headers)

    assert detail_response.status_code == 200
    assert detail_response.json()["request"]["boundingBox"]["minLatitude"] == 52.52
    assert session_detail.status_code == 200
    assert session_detail.json()["session"]["durationSeconds"] == 11


def test_dashboard_renders_operator_ui(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.post("/live-location", json=valid_payload())

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Receiver-Dashboard" in response.text
    assert "Jüngste Requests" in response.text
    assert "52.52" in response.text


def test_dashboard_navigation_pages_render(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    ingest_response = client.post("/live-location", json=valid_payload())
    request_id = ingest_response.json()["requestId"]
    session_id = "123e4567-e89b-12d3-a456-426614174000"
    point_id = query_scalar(tmp_path, "SELECT id FROM gps_points ORDER BY id ASC LIMIT 1")
    headers = basic_auth_headers("operator", "dashboard-pass")

    paths = [
        "/dashboard",
        "/dashboard/live-status",
        "/dashboard/activity",
        "/dashboard/points",
        f"/dashboard/points/{point_id}",
        "/dashboard/requests",
        f"/dashboard/requests/{request_id}",
        "/dashboard/sessions",
        f"/dashboard/sessions/{session_id}",
        "/dashboard/exports",
        "/dashboard/config",
        "/dashboard/storage",
        "/dashboard/security",
        "/dashboard/system",
        "/dashboard/troubleshooting",
        "/dashboard/open-items",
    ]

    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert "LH2GPX Receiver" in response.text, path


def test_config_summary_masks_secrets(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        bearer_token="secret-token",
        admin_username="operator",
        admin_password="dashboard-pass",
    )

    response = client.get("/api/config-summary", headers=basic_auth_headers("operator", "dashboard-pass"))

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["bearerToken"] == "set(len=12)"
    assert config["adminPassword"] == "set(len=14)"
    assert "secret-token" not in response.text
    assert "dashboard-pass" not in response.text


def test_logs_do_not_include_bearer_token(tmp_path: Path, caplog) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    with caplog.at_level("INFO"):
        response = client.post(
            "/live-location",
            json=valid_payload(),
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 202
    joined = "\n".join(record.message for record in caplog.records)
    assert "secret-token" not in joined


def test_import_status_exposes_server_metrics(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    client.app.state.inline_import_tasks = True
    headers = basic_auth_headers("operator", "dashboard-pass")
    gpx = (
        b'<?xml version="1.0"?><gpx version="1.1" creator="t"><trk><trkseg>'
        b'<trkpt lat="52.52" lon="13.405"><time>2026-04-23T12:00:00Z</time></trkpt>'
        b'<trkpt lat="52.5201" lon="13.4051"><time>2026-04-23T12:01:00Z</time></trkpt>'
        b'</trkseg></trk></gpx>'
    )

    response = client.post("/api/import", headers=headers, files={"file": ("track.gpx", gpx, "application/gpx+xml")})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["file_size_bytes"] == len(gpx)
    task_id = body["task_id"]

    task = None
    for _ in range(50):
        status_response = client.get(f"/api/import/status/{task_id}", headers=headers)
        assert status_response.status_code == 200
        task = status_response.json()
        if task["status"] in {"done", "error"}:
            break
        time.sleep(0.01)

    assert task is not None
    assert task["status"] == "done"
    assert task["detected_format"] == "gpx"
    assert task["metrics"]["rawPoints"] == 2
    assert task["metrics"]["inserted"] == 2
    assert task["metrics"]["skippedTotal"] == 0
    assert task["metrics"]["parseDurationMs"] >= 0
    assert task["metrics"]["insertDurationMs"] >= 0
    assert task["session_id"].startswith("import-")


def test_parse_zip_supports_geo_dot_json_entries() -> None:
    geojson = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [13.405, 52.52]},
                    "properties": {"timestamp": "2026-04-23T12:00:00Z"},
                }
            ],
        }
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("export.geo.json", geojson)

    report = parse_file_report("archive.zip", buffer.getvalue())

    assert report["detected_format"] == "zip"
    assert report["archive_entries_total"] == 1
    assert report["archive_entries_used"] == 1
    assert report["archive_entries_failed"] == 0
    assert len(report["points"]) == 1


def make_client(
    tmp_path: Path,
    *,
    bearer_token: str | None = None,
    admin_username: str | None = None,
    admin_password: str | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    settings = Settings(
        bind_host="127.0.0.1",
        port=8080,
        public_hostname="localhost",
        public_base_url="http://localhost:8080",
        bearer_token=bearer_token,
        admin_username=admin_username,
        admin_password=admin_password,
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "data" / "receiver.sqlite3",
        raw_payload_ndjson_path=tmp_path / "data" / "raw-payloads.ndjson",
        legacy_request_ndjson_path=tmp_path / "data" / "live-location.ndjson",
        raw_payload_ndjson_enabled=True,
        local_timezone="UTC",
        log_level="INFO",
        request_body_max_bytes=262144,
        points_page_size_default=50,
        points_page_size_max=250,
        rate_limit_requests_per_minute=0,
        trust_proxy_headers=True,
    )
    return TestClient(create_app(settings), raise_server_exceptions=raise_server_exceptions)


def valid_payload() -> dict[str, object]:
    return {
        "source": "LocationHistory2GPX-iOS",
        "sessionID": "123e4567-e89b-12d3-a456-426614174000",
        "captureMode": "foregroundWhileInUse",
        "sentAt": "2026-03-20T12:00:10Z",
        "points": [
            {
                "latitude": 52.52,
                "longitude": 13.405,
                "timestamp": "2026-03-20T11:59:59Z",
                "horizontalAccuracyM": 6.5,
                "extraPointField": "kept",
            },
            {
                "latitude": 52.521,
                "longitude": 13.406,
                "timestamp": "2026-03-20T12:00:10Z",
                "horizontalAccuracyM": 5.1,
            },
        ],
        "extraTopLevel": {"device": "iPhone 15 Pro Max"},
    }


def basic_auth_headers(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def query_scalar(tmp_path: Path, sql: str) -> int:
    with sqlite3.connect(tmp_path / "data" / "receiver.sqlite3") as connection:
        return int(connection.execute(sql).fetchone()[0])


def query_text(tmp_path: Path, sql: str) -> str:
    with sqlite3.connect(tmp_path / "data" / "receiver.sqlite3") as connection:
        value = connection.execute(sql).fetchone()[0]
    return str(value)


def read_raw_payload_file(tmp_path: Path) -> list[dict[str, object]]:
    raw_path = tmp_path / "data" / "raw-payloads.ndjson"
    return [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
