from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.main import (
    _POINTS_CACHE,
    _MAP_META_CACHE,
    _MAP_DATA_CACHE,
    _TIMELINE_PREVIEW_CACHE,
    _HEATMAP_LAYER_CACHE,
    _TRACK_CONTEXT_CACHE,
    _TRACK_LAYER_CACHE,
    _SNAP_CACHE,
    _invalidate_data_caches,
)
from tests.test_app import make_client, basic_auth_headers, valid_payload
from app.storage import StorageError

def test_dashboard_map_accepts_query_parameters(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    # Test with session_id
    response = client.get("/dashboard/map?session_id=test-session", headers=headers)
    assert response.status_code == 200
    assert "test-session" in response.text
    
    # Test with import_session
    response = client.get("/dashboard/map?import_session=import-test", headers=headers)
    assert response.status_code == 200
    assert "import-test" in response.text

def test_invalidate_data_caches_clears_all_caches() -> None:
    # Fill caches with dummy data
    caches = [
        _POINTS_CACHE, _MAP_META_CACHE, _MAP_DATA_CACHE, _TIMELINE_PREVIEW_CACHE,
        _HEATMAP_LAYER_CACHE, _TRACK_CONTEXT_CACHE, _TRACK_LAYER_CACHE, _SNAP_CACHE
    ]
    for c in caches:
        c["test"] = (1.0, "etag", b"body")
        assert len(c) > 0
    
    _invalidate_data_caches()
    
    for c in caches:
        assert len(c) == 0

@patch("app.main.manager.broadcast")
def test_import_invalidates_caches_and_broadcasts(mock_broadcast: MagicMock, tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    client.app.state.inline_import_tasks = True
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    # Fill cache
    _POINTS_CACHE["stale"] = (1.0, "etag", b"body")
    
    # Perform import
    import_data = json.dumps([
        {"latitude": 52.5, "longitude": 13.4, "timestamp_utc": "2026-04-25T12:00:00Z"}
    ]).encode("utf-8")
    
    files = {"file": ("test.json", import_data, "application/json")}
    response = client.post("/api/import", files=files, headers=headers)
    
    assert response.status_code == 200
    assert len(_POINTS_CACHE) == 0  # Cache should be invalidated
    
    # Check broadcast
    mock_broadcast.assert_called()
    calls = [call[0][0]["type"] for call in mock_broadcast.call_args_list]
    assert "import_completed" in calls

@patch("app.main.manager.broadcast")
def test_session_delete_invalidates_caches_and_broadcasts(mock_broadcast: MagicMock, tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    # Create a session
    client.post("/live-location", json=valid_payload())
    session_id = "123e4567-e89b-12d3-a456-426614174000"
    
    # Fill cache
    _POINTS_CACHE["stale"] = (1.0, "etag", b"body")
    
    # Delete session
    response = client.delete(f"/api/sessions/{session_id}", headers=headers)
    
    assert response.status_code == 200
    assert len(_POINTS_CACHE) == 0  # Cache should be invalidated
    
    # Check broadcast
    mock_broadcast.assert_called()
    assert mock_broadcast.call_args[0][0]["type"] == "session_deleted"
    assert mock_broadcast.call_args[0][0]["sessionId"] == session_id
    assert mock_broadcast.call_args[0][0]["deleted"] > 0

def test_storage_dashboard_snapshot_includes_fields(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    snapshot = client.app.state.storage.get_dashboard_snapshot()
    assert "sqliteWalFile" in snapshot["storage"]
    assert "sqliteShmFile" in snapshot["storage"]
    
    response = client.get("/dashboard/storage", headers=headers)
    assert response.status_code == 200
    assert "SQLite Groesse" in response.text

def test_storage_dashboard_fallback_does_not_crash(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        admin_username="operator",
        admin_password="dashboard-pass",
        raise_server_exceptions=False,
    )
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    def fail_snapshot():
        raise StorageError("forced failure")
    
    # Mock storage.get_dashboard_snapshot on the storage instance
    with patch.object(client.app.state.storage, "get_dashboard_snapshot", side_effect=fail_snapshot):
        response = client.get("/dashboard/storage", headers=headers)
        assert response.status_code == 200
        assert "Speicher" in response.text
        # Check if fallback fields are present in HTML
        assert "SQLite Groesse" in response.text
        assert "SQLite zuletzt geaendert" in response.text

def test_historical_import_guarantees_full_refresh_via_client(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    client.app.state.inline_import_tasks = True
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    # 1. Newest point
    client.post("/live-location", json=valid_payload())
    first = client.get("/api/map-data?page_size=1000", headers=headers)
    assert first.status_code == 200
    assert first.json()["meta"]["totalPoints"] == 2
    
    # 2. Historical import (older than latest)
    import_data = json.dumps([
        {
            "latitude": 52.6,
            "longitude": 13.5,
            "timestamp": "2025-01-01T12:00:00Z",
        }
    ]).encode("utf-8")
    
    client.post(
        "/api/import",
        files={"file": ("old.json", import_data, "application/json")},
        headers=headers,
    )
    
    # 3. Simulate client-side cache clear (no latest_known_ts sent)
    # The server MUST return 200 and include the new point in totals.
    full_refresh = client.get("/api/map-data?page_size=1000", headers=headers)
    assert full_refresh.status_code == 200
    assert full_refresh.json()["meta"]["totalPoints"] == 3
    
    # Verify the historical point is present in logItems
    lats = [p["lat"] for p in full_refresh.json()["logItems"]]
    assert 52.6 in lats
