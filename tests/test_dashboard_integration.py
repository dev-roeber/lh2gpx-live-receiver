from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import (
    create_app,
    _POINTS_CACHE,
    _MAP_META_CACHE,
    _invalidate_data_caches,
)
from tests.test_app import make_client, basic_auth_headers, valid_payload

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
    _POINTS_CACHE["test"] = (1.0, "etag", b"body")
    _MAP_META_CACHE["test"] = (1.0, "etag", b"body")
    
    assert len(_POINTS_CACHE) > 0
    assert len(_MAP_META_CACHE) > 0
    
    _invalidate_data_caches()
    
    assert len(_POINTS_CACHE) == 0
    assert len(_MAP_META_CACHE) == 0

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

def test_storage_dashboard_snapshot_includes_wal_shm(tmp_path: Path) -> None:
    client = make_client(tmp_path, admin_username="operator", admin_password="dashboard-pass")
    headers = basic_auth_headers("operator", "dashboard-pass")
    
    # Check snapshot data directly
    snapshot = client.app.state.storage.get_dashboard_snapshot()
    assert "sqliteWalFile" in snapshot["storage"]
    assert "sqliteShmFile" in snapshot["storage"]
    
    response = client.get("/dashboard/storage", headers=headers)
    assert response.status_code == 200
    # The fields should be present in HTML if we force them to exist, 
    # but we already verified they are in the snapshot.
