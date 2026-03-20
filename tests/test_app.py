from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoint_returns_service_status(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "lh2gpx-live-receiver"
    assert body["authRequired"] is False
    assert body["dataFile"].endswith("live-location.ndjson")
    assert "time" in body


def test_auth_required_rejects_missing_bearer_token(tmp_path: Path) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid bearer token."


def test_auth_required_accepts_valid_bearer_token_and_persists_payload(tmp_path: Path) -> None:
    client = make_client(tmp_path, bearer_token="secret-token")

    response = client.post(
        "/live-location",
        json=valid_payload(),
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    stored_line = read_single_stored_line(tmp_path)
    assert stored_line["source"] == "LocationHistory2GPX-iOS"
    assert stored_line["sessionID"] == "123e4567-e89b-12d3-a456-426614174000"
    assert stored_line["extraTopLevel"] == {"device": "iPhone 15 Pro Max"}
    assert stored_line["points"][0]["extraPointField"] == "kept"
    assert "receivedAt" in stored_line


def test_valid_payload_without_auth_is_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/live-location", json=valid_payload())

    assert response.status_code == 202
    assert response.json()["pointsAccepted"] == 1
    stored_line = read_single_stored_line(tmp_path)
    assert stored_line["captureMode"] == "foregroundWhileInUse"


def test_accept_log_contains_location_summary(tmp_path: Path, capsys) -> None:
    client = make_client(tmp_path)

    response = client.post("/live-location", json=valid_payload())
    captured = capsys.readouterr()

    assert response.status_code == 202
    assert "pts=1" in captured.err
    assert "first=52.520000,13.405000" in captured.err
    assert "last=52.520000,13.405000" in captured.err
    assert "firstTs=2026-03-20T11:59:59+00:00" in captured.err
    assert "lastTs=2026-03-20T11:59:59+00:00" in captured.err
    assert "session=123e4567-e89b-12d3-a456-426614174000" in captured.err
    assert "source=LocationHistory2GPX-iOS" in captured.err
    assert "mode=foregroundWhileInUse" in captured.err


def test_invalid_payload_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    payload = valid_payload()
    payload["points"][0]["latitude"] = 181

    response = client.post("/live-location", json=payload)

    assert response.status_code == 422
    assert not data_file(tmp_path).exists()


def make_client(tmp_path: Path, bearer_token: str | None = None) -> TestClient:
    settings = Settings(
        bind_host="127.0.0.1",
        port=8080,
        bearer_token=bearer_token,
        data_dir=tmp_path / "data",
        log_level="INFO",
    )
    app = create_app(settings)
    return TestClient(app)


def valid_payload() -> dict[str, object]:
    return {
        "source": "LocationHistory2GPX-iOS",
        "sessionID": "123e4567-e89b-12d3-a456-426614174000",
        "captureMode": "foregroundWhileInUse",
        "sentAt": "2026-03-20T12:00:00Z",
        "points": [
            {
                "latitude": 52.52,
                "longitude": 13.405,
                "timestamp": "2026-03-20T11:59:59Z",
                "horizontalAccuracyM": 6.5,
                "extraPointField": "kept",
            }
        ],
        "extraTopLevel": {"device": "iPhone 15 Pro Max"},
    }


def read_single_stored_line(tmp_path: Path) -> dict[str, object]:
    lines = data_file(tmp_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def data_file(tmp_path: Path) -> Path:
    return tmp_path / "data" / "live-location.ndjson"
