from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app import dawarich_sync
from app.config import Settings
from app.storage import ReceiverStorage


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Result:
        self.query = query
        self.params = params
        return _Result(self.rows)


def test_initial_point_fetch_uses_bounded_keyset() -> None:
    connection = _Connection([])

    assert dawarich_sync._fetch_points(connection, after_id=500, max_id=1200) == []

    assert "OFFSET" not in connection.query.upper()
    assert "id > %s" in connection.query
    assert "id <= %s" in connection.query
    assert "ORDER BY id" in connection.query
    assert connection.params == (500, 1200, dawarich_sync.BATCH_SIZE)


def test_initial_point_fetch_requires_stable_barrier() -> None:
    connection = _Connection([])

    with pytest.raises(ValueError, match="max_id is required"):
        dawarich_sync._fetch_points(connection, after_id=500)

    assert connection.query == ""


def _storage(tmp_path: Path) -> ReceiverStorage:
    data_dir = tmp_path / "data"
    storage = ReceiverStorage(
        Settings(
            bind_host="127.0.0.1",
            port=8082,
            public_hostname="localhost",
            public_base_url="http://localhost:8082",
            bearer_token=None,
            data_dir=data_dir,
            sqlite_path=data_dir / "receiver.sqlite3",
            raw_payload_ndjson_path=data_dir / "raw-payloads.ndjson",
            legacy_request_ndjson_path=data_dir / "live-location.ndjson",
            raw_payload_ndjson_enabled=False,
            local_timezone="UTC",
            log_level="INFO",
            request_body_max_bytes=262144,
            points_page_size_default=50,
            points_page_size_max=250,
            rate_limit_requests_per_minute=0,
            trust_proxy_headers=True,
        )
    )
    storage.startup()
    assert storage.readiness().is_ready
    return storage


def test_sync_state_preserves_initial_state_and_explicit_error_updates(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    storage.set_dawarich_sync_state(last_event_id=0, last_error="initialising")
    assert storage.get_dawarich_sync_state() == {
        "provider": "dawarich",
        "last_event_id": 0,
        "last_success_at": None,
        "last_error": "initialising",
    }

    storage.set_dawarich_sync_state(last_event_id=12, last_success_at="2026-09-06T10:00:00Z")
    storage.set_dawarich_sync_state(last_event_id=7, last_error="late failure")
    state = storage.get_dawarich_sync_state()

    assert state["last_event_id"] == 12
    assert state["last_success_at"] == "2026-09-06T10:00:00Z"
    assert state["last_error"] == "late failure"

    # A successful update explicitly clears the error without changing the
    # cursor when its event id is older than the durable cursor.
    storage.set_dawarich_sync_state(
        last_event_id=9,
        last_success_at="2026-09-06T10:01:00Z",
        last_error=None,
    )
    state = storage.get_dawarich_sync_state()
    assert state["last_event_id"] == 12
    assert state["last_success_at"] == "2026-09-06T10:01:00Z"
    assert state["last_error"] is None


def test_sync_state_is_monotonic_for_concurrent_out_of_order_writes(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.set_dawarich_sync_state(last_event_id=100)

    def write(event_id: int) -> None:
        storage.set_dawarich_sync_state(last_event_id=event_id, last_error=f"event {event_id}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, [12, 450, 37, 901, 88, 640, 3, 777]))

    state = storage.get_dawarich_sync_state()
    assert state["last_event_id"] == 901
    assert state["last_error"] in {"event 12", "event 450", "event 37", "event 901", "event 88", "event 640", "event 3", "event 777"}


def _dawarich_point(point_id: int) -> dict:
    return {
        "id": point_id,
        "user_id": 1,
        "latitude": 51.0,
        "longitude": 7.0,
        "timestamp": 1_725_600_000,
        "accuracy": 5,
        "updated_at": None,
        "payload_hash": f"hash-{point_id}",
    }


def test_startup_removes_orphaned_dawarich_mappings(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.upsert_dawarich_points([_dawarich_point(10)])

    with storage._locked_transaction() as connection:
        valid_mapping = connection.execute(
            "SELECT receiver_point_id FROM external_points WHERE provider='dawarich' AND external_id='10'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO external_points(provider, external_id, receiver_point_id, dawarich_user_id) VALUES (?, ?, ?, ?)",
            ("dawarich", "999", 999999, "1"),
        )

    restarted = ReceiverStorage(storage.settings)
    restarted.startup()
    assert restarted.readiness().is_ready

    with restarted._connect() as connection:
        mappings = connection.execute(
            "SELECT external_id, receiver_point_id FROM external_points WHERE provider='dawarich' ORDER BY external_id"
        ).fetchall()

    assert [(row["external_id"], row["receiver_point_id"]) for row in mappings] == [("10", valid_mapping)]


def test_upsert_recreates_mapping_after_receiver_point_was_removed(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    point = _dawarich_point(20)
    storage.upsert_dawarich_points([point])

    with storage._locked_transaction() as connection:
        receiver_point_id = connection.execute(
            "SELECT receiver_point_id FROM external_points WHERE provider='dawarich' AND external_id='20'"
        ).fetchone()[0]
        connection.execute("DELETE FROM gps_points WHERE id = ?", (receiver_point_id,))

    result = storage.upsert_dawarich_points([point])
    assert result == {"inserted": 1, "updated": 0, "invalid": 0}

    with storage._connect() as connection:
        mapping = connection.execute(
            "SELECT receiver_point_id FROM external_points WHERE provider='dawarich' AND external_id='20'"
        ).fetchone()
        assert mapping is not None
        assert connection.execute(
            "SELECT 1 FROM gps_points WHERE id = ?", (mapping["receiver_point_id"],)
        ).fetchone() is not None
