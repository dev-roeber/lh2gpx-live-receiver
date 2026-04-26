from __future__ import annotations

import datetime as dt
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import _HEATMAP_LAYER_CACHE, _resolve_heatmap_layer
from app.models import LiveLocationPoint, LiveLocationRequest, PointFilters, RequestMetadata
from app.storage import ReceiverStorage


def make_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "receiver.sqlite3"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        bind_host="127.0.0.1",
        port=8000,
        public_hostname="localhost",
        public_base_url="http://localhost:8000",
        bearer_token=None,
        admin_username=None,
        admin_password=None,
        data_dir=data_dir,
        sqlite_path=db_path,
        raw_payload_ndjson_path=data_dir / "raw.ndjson",
        legacy_request_ndjson_path=data_dir / "legacy.ndjson",
        raw_payload_ndjson_enabled=False,
        local_timezone="UTC",
        log_level="INFO",
        request_body_max_bytes=1024 * 1024,
        points_page_size_default=1000,
        points_page_size_max=200000,
        rate_limit_requests_per_minute=0,
        trust_proxy_headers=False,
    )
    return TestClient(main_module.create_app(settings))


def _ingest_points(storage: ReceiverStorage, session_id: UUID, *, start: dt.datetime, count: int) -> None:
    chunk_size = 5000
    for offset in range(0, count, chunk_size):
        points = []
        for index in range(offset, min(offset + chunk_size, count)):
            points.append(
                LiveLocationPoint(
                    timestamp=start - dt.timedelta(seconds=index),
                    latitude=52.52 + (index * 0.000001),
                    longitude=13.40 + (index * 0.000001),
                    horizontalAccuracyM=5.0,
                )
            )
        payload = LiveLocationRequest(
            sessionID=session_id,
            source="test",
            captureMode="active",
            sentAt=start,
            points=points,
        )
        metadata = RequestMetadata(
            request_id=f"req_{offset}",
            received_at_utc=start,
            remote_addr="127.0.0.1",
            proxied_ip="",
            user_agent="test",
            request_path="/live-location",
            request_method="POST",
        )
        storage.ingest_success(payload, metadata, "{}")


def seed_points(tmp_path: Path, count: int = 1000) -> str:
    client = make_client(tmp_path)
    storage = client.app.state.storage
    session_id = uuid4()
    _ingest_points(storage, session_id, start=dt.datetime.now(dt.timezone.utc), count=count)
    return str(session_id)


def append_new_point(storage: ReceiverStorage, session_id: str) -> None:
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
    payload = LiveLocationRequest(
        sessionID=UUID(session_id),
        source="test",
        captureMode="active",
        sentAt=now,
        points=[
            LiveLocationPoint(
                timestamp=now,
                latitude=52.531,
                longitude=13.411,
                horizontalAccuracyM=4.0,
            )
        ],
    )
    metadata = RequestMetadata(
        request_id="req_new",
        received_at_utc=now,
        remote_addr="127.0.0.1",
        proxied_ip="",
        user_agent="test",
        request_path="/live-location",
        request_method="POST",
    )
    storage.ingest_success(payload, metadata, "{}")


def test_large_bbox_uses_sampled_points(tmp_path: Path) -> None:
    session_id = seed_points(tmp_path, count=1000)
    client = make_client(tmp_path)
    storage = client.app.state.storage
    original_sampled = storage.list_points_in_bbox_sampled
    original_full = storage.list_points_in_bbox
    calls = {"sampled": 0, "full": 0}

    def wrapped_sampled(*args, **kwargs):
        calls["sampled"] += 1
        return original_sampled(*args, **kwargs)

    def wrapped_full(*args, **kwargs):
        calls["full"] += 1
        return original_full(*args, **kwargs)

    storage.list_points_in_bbox_sampled = wrapped_sampled
    storage.list_points_in_bbox = wrapped_full

    response = client.get(
        f"/api/map-data?bbox=13.3,52.4,13.5,52.6&zoom=12&include_points=true&include_accuracy=false&include_polyline=false&include_labels=false&include_speed=false&include_stops=false&include_daytrack=false&include_snap=false&session_id={session_id}"
    )
    assert response.status_code == 200
    assert calls["sampled"] == 1
    assert response.json()["meta"]["loadedPoints"] < response.json()["meta"]["visiblePoints"]


def test_track_context_never_uses_sampled_points(tmp_path: Path, monkeypatch) -> None:
    session_id = seed_points(tmp_path, count=1000)
    client = make_client(tmp_path)
    storage = client.app.state.storage
    original_resolve_track_context = main_module._resolve_track_context
    sampled_used = {"value": False}
    preloaded_values = []

    original_sampled = storage.list_points_in_bbox_sampled

    def wrapped_sampled(*args, **kwargs):
        sampled_used["value"] = True
        return original_sampled(*args, **kwargs)

    def wrapped_track_context(*args, **kwargs):
        preloaded_values.append(kwargs.get("preloaded_points_desc"))
        return original_resolve_track_context(*args, **kwargs)

    storage.list_points_in_bbox_sampled = wrapped_sampled
    monkeypatch.setattr(main_module, "_resolve_track_context", wrapped_track_context)

    response = client.get(
        f"/api/map-data?bbox=13.3,52.4,13.5,52.6&zoom=12&include_points=true&include_polyline=true&session_id={session_id}"
    )
    assert response.status_code == 200
    assert sampled_used["value"] is True
    assert preloaded_values
    assert preloaded_values[-1] is None


def test_delta_request_with_new_points_does_not_force_full_viewport_load(tmp_path: Path) -> None:
    session_id = seed_points(tmp_path, count=1000)
    client = make_client(tmp_path)
    storage = client.app.state.storage
    base_response = client.get(
        f"/api/map-data?bbox=13.3,52.4,13.5,52.6&zoom=12&include_points=true&include_accuracy=false&include_polyline=false&include_labels=false&include_speed=false&include_stops=false&include_daytrack=false&include_snap=false&session_id={session_id}"
    )
    latest_ts = base_response.json()["meta"]["latestVisiblePointTsUtc"]
    append_new_point(storage, session_id)

    original_sampled = storage.list_points_in_bbox_sampled
    original_full = storage.list_points_in_bbox
    original_since = storage.list_points_since
    calls = {"sampled": 0, "full": 0, "since": 0}

    def wrapped_sampled(*args, **kwargs):
        calls["sampled"] += 1
        return original_sampled(*args, **kwargs)

    def wrapped_full(*args, **kwargs):
        calls["full"] += 1
        return original_full(*args, **kwargs)

    def wrapped_since(*args, **kwargs):
        calls["since"] += 1
        return original_since(*args, **kwargs)

    storage.list_points_in_bbox_sampled = wrapped_sampled
    storage.list_points_in_bbox = wrapped_full
    storage.list_points_since = wrapped_since

    delta_response = client.get(
        f"/api/map-data?bbox=13.3,52.4,13.5,52.6&zoom=12&include_points=true&include_accuracy=false&include_polyline=false&include_labels=false&include_speed=false&include_stops=false&include_daytrack=false&include_snap=false&session_id={session_id}&latest_known_ts={latest_ts}"
    )
    assert delta_response.status_code == 200
    assert calls["sampled"] == 1
    assert calls["since"] == 1
    assert calls["full"] == 0


def test_heatmap_only_does_not_load_full_viewport_points(tmp_path: Path) -> None:
    seed_points(tmp_path, count=1000)
    client = make_client(tmp_path)
    storage = client.app.state.storage
    calls = {"full": 0, "sampled": 0, "list": 0}

    original_full = storage.list_points_in_bbox
    original_sampled = storage.list_points_in_bbox_sampled
    original_list = storage.list_points

    def wrapped_full(*args, **kwargs):
        calls["full"] += 1
        return original_full(*args, **kwargs)

    def wrapped_sampled(*args, **kwargs):
        calls["sampled"] += 1
        return original_sampled(*args, **kwargs)

    def wrapped_list(*args, **kwargs):
        calls["list"] += 1
        return original_list(*args, **kwargs)

    storage.list_points_in_bbox = wrapped_full
    storage.list_points_in_bbox_sampled = wrapped_sampled
    storage.list_points = wrapped_list

    response = client.get(
        "/api/map-data?bbox=13.3,52.4,13.5,52.6&zoom=12&include_points=false&include_accuracy=false&include_heatmap=true&include_polyline=false&include_labels=false&include_speed=false&include_stops=false&include_daytrack=false&include_snap=false"
    )
    assert response.status_code == 200
    assert response.json()["meta"]["loadedPoints"] == 0
    assert calls == {"full": 0, "sampled": 0, "list": 0}


def test_label_toggle_controls_line_labels() -> None:
    map_template = Path("/home/sebastian/repos/lh2gpx-live-receiver/app/templates/map.html").read_text()
    assert "labels: ['layer-line-labels']" in map_template
    assert "!layerDataLoaded.labels" in map_template
    assert "updateLayerVisibility('labels', labelsActive)" in map_template


def test_heatmap_cache_key_matches_query_bbox() -> None:
    class FakeStorage:
        def __init__(self) -> None:
            self.calls = []

        def list_heatmap_points(self, filters, *, bbox=None, spatial_zoom_hint=None):
            self.calls.append((bbox, spatial_zoom_hint))
            return []

    _HEATMAP_LAYER_CACHE.clear()
    storage = FakeStorage()
    filters = PointFilters()
    bbox_a = (13.4001, 52.5201, 13.4999, 52.5999)
    bbox_b = (13.4002, 52.5202, 13.4998, 52.5998)

    _resolve_heatmap_layer(storage, filters, bbox=bbox_a, zoom=12)
    _resolve_heatmap_layer(storage, filters, bbox=bbox_b, zoom=12)

    assert len(storage.calls) == 1
    queried_bbox, queried_zoom = storage.calls[0]
    assert queried_bbox == main_module._bucket_bbox_for_zoom(bbox_a, zoom=12)
    assert queried_zoom == 12
