from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Callable

from fastapi import Depends, FastAPI, Query, Request, Response

from ..auth import require_admin_access
from ..models import PointFilters


@dataclass(frozen=True)
class MapApiDependencies:
    settings: Callable[[Request], Any]
    storage: Callable[[Request], Any]
    cache_get: Callable[..., tuple[Any, ...] | None]
    cache_put: Callable[..., None]
    parse_bbox: Callable[[str | None], tuple[float, float, float, float] | None]
    expand_bbox: Callable[..., tuple[float, float, float, float]]
    summarize_import_tasks: Callable[[], dict[str, Any]]
    adaptive_timeline_sample: Callable[..., list[dict[str, Any]]]
    build_timeline_markers: Callable[..., list[dict[str, Any]]]
    prepare_timeline_preview_payload: Callable[..., dict[str, Any]]
    prepare_map_payload: Callable[..., dict[str, Any]]
    prepare_map_delta_payload: Callable[..., dict[str, Any]]
    resolve_heatmap_layer: Callable[..., list[dict[str, Any]]]
    resolve_track_context: Callable[..., dict[str, Any]]
    resolve_track_layers: Callable[..., dict[str, Any]]
    parse_iso_timestamp: Callable[[str | None], Any]
    target_point_limit: Callable[[int, int], int]
    serialize_polyline_segments: Callable[..., list[dict[str, Any]]]
    serialize_speed_segments: Callable[..., list[dict[str, Any]]]
    detect_stops: Callable[..., list[dict[str, Any]]]
    serialize_snap_segments: Callable[..., list[dict[str, Any]]]
    build_delta_context_points_asc: Callable[..., list[dict[str, Any]]]
    segment_track: Callable[..., list[list[dict[str, Any]]]]
    bucket_bbox_for_zoom: Callable[..., tuple[float, float, float, float] | None]
    points_cache: dict[str, tuple[float, str, bytes]]
    points_cache_ttl: float
    points_cache_max: int
    timeline_preview_cache: dict[str, tuple[float, str, bytes]]
    timeline_preview_cache_ttl: float
    map_meta_cache: dict[str, tuple[float, str, bytes]]
    map_meta_cache_ttl: float
    map_data_cache: dict[str, tuple[float, str, bytes]]
    map_data_cache_ttl: float
    body_cache_max: int
    map_data_page_size_max: int


def register_map_api_routes(app: FastAPI, deps: MapApiDependencies) -> None:
    @app.get("/api/timeline", dependencies=[Depends(require_admin_access)])
    async def api_timeline(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        search: str | None = Query(default=None),
        bbox: str | None = Query(default=None),
        stop_min_duration_min: int = Query(default=5, ge=1, le=240),
        stop_radius_m: int = Query(default=100, ge=10, le=5000),
        limit: int = Query(default=50000, ge=1, le=50000),
    ) -> Response:
        viewport_bbox = deps.parse_bbox(bbox)
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            search=search,
            page=1,
            page_size=1,
        )
        cache_key = f"timeline:{request.url.query}"
        cached = deps.cache_get(deps.points_cache, cache_key, ttl=deps.points_cache_ttl)
        if cached:
            _, etag, body = cached
        else:
            now = time.time()
            raw_items = deps.storage(request).list_timeline_points(filters, bbox=viewport_bbox, limit=50000)
            items = deps.adaptive_timeline_sample(raw_items, limit=limit)
            precomputed_day_markers = None
            if viewport_bbox is None:
                precomputed_day_markers = deps.storage(request).list_precomputed_timeline_day_markers(filters)
            markers = deps.build_timeline_markers(
                raw_items,
                stop_min_duration_min=stop_min_duration_min,
                stop_radius_m=stop_radius_m,
                precomputed_day_markers=precomputed_day_markers,
            )
            result = {
                "requestId": request.state.request_id,
                "timeline": {
                    "items": [
                        {
                            "id": item["id"],
                            "timestampUtc": item["point_timestamp_utc"],
                            "timestampLocal": item["point_timestamp_local"],
                            "latitude": item["latitude"],
                            "longitude": item["longitude"],
                            "horizontal_accuracy_m": item["horizontal_accuracy_m"],
                            "session_id": item["session_id"],
                            "source": item["source"],
                            "capture_mode": item["capture_mode"],
                        }
                        for item in items
                    ],
                    "count": len(items),
                    "meta": {
                        "minTimestampUtc": items[0]["point_timestamp_utc"] if items else None,
                        "maxTimestampUtc": items[-1]["point_timestamp_utc"] if items else None,
                        "truncated": len(raw_items) > len(items),
                        "bboxFiltered": viewport_bbox is not None,
                        "rawCount": len(raw_items),
                        "sampledCount": len(items),
                    },
                    "markers": markers,
                },
            }
            body = json.dumps(result, separators=(",", ":")).encode()
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            deps.cache_put(
                deps.points_cache,
                cache_key,
                (now, etag, body),
                ttl=deps.points_cache_ttl,
                max_items=deps.points_cache_max,
            )
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"})
        return Response(content=body, media_type="application/json", headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"})

    @app.get("/api/timeline-preview", dependencies=[Depends(require_admin_access)])
    async def api_timeline_preview(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        bbox: str | None = Query(default=None),
        page_size: int | None = Query(default=None, ge=1),
        log_limit: int | None = Query(default=None, ge=1),
        zoom: float = Query(default=12, ge=1, le=22),
        route_time_gap_min: int = Query(default=15, ge=1, le=1440),
        route_dist_gap_m: int = Query(default=1200, ge=10, le=50000),
        stop_min_duration_min: int = Query(default=5, ge=1, le=240),
        stop_radius_m: int = Query(default=100, ge=10, le=5000),
        include_points: bool = Query(default=True),
        include_heatmap: bool = Query(default=False),
        include_polyline: bool = Query(default=True),
        include_accuracy: bool = Query(default=False),
        include_labels: bool = Query(default=False),
        include_speed: bool = Query(default=False),
        include_stops: bool = Query(default=False),
        include_daytrack: bool = Query(default=False),
        include_snap: bool = Query(default=False),
    ) -> Response:
        request_started_at = time.perf_counter()
        configured_max = max(1, deps.settings(request).points_page_size_max)
        effective_page_size = min(page_size or configured_max, configured_max, deps.map_data_page_size_max)
        effective_log_limit = min(log_limit or effective_page_size, effective_page_size)
        effective_zoom = max(1, min(22, round(zoom)))
        viewport_bbox = deps.parse_bbox(bbox)
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            page=1,
            page_size=effective_page_size,
        )
        cache_key = f"timeline-preview:{request.url.query}"
        cached = deps.cache_get(deps.timeline_preview_cache, cache_key, ttl=deps.timeline_preview_cache_ttl)
        cache_state = "miss"
        counts_duration_ms = 0.0
        preview_duration_ms = 0.0
        serialize_duration_ms = 0.0
        if cached:
            _, etag, body = cached
            cache_state = "hit"
        else:
            now = time.time()
            storage = deps.storage(request)
            counts_started_at = time.perf_counter()
            if viewport_bbox:
                viewport_items = storage.list_points_in_bbox(filters, bbox=viewport_bbox, spatial_zoom_hint=effective_zoom)
                visible_points = len(viewport_items)
                total_points = storage.count_points(filters)
            else:
                listed = storage.list_points(filters)
                viewport_items = listed["items"]
                visible_points = len(viewport_items)
                total_points = listed["total"]
            counts_duration_ms = round((time.perf_counter() - counts_started_at) * 1000, 2)
            preview_started_at = time.perf_counter()
            payload = await asyncio.to_thread(
                deps.prepare_timeline_preview_payload,
                viewport_items,
                total_points=total_points,
                visible_points=visible_points,
                log_limit=effective_log_limit,
                zoom=effective_zoom,
                include_points=include_points,
                include_accuracy=include_accuracy,
                include_polyline=include_polyline or include_labels,
                include_labels=include_labels,
                route_time_gap_min=route_time_gap_min,
                route_dist_gap_m=route_dist_gap_m,
            )
            preview_duration_ms = round((time.perf_counter() - preview_started_at) * 1000, 2)
            if viewport_bbox:
                payload["meta"]["bbox"] = {
                    "minLon": viewport_bbox[0],
                    "minLat": viewport_bbox[1],
                    "maxLon": viewport_bbox[2],
                    "maxLat": viewport_bbox[3],
                }
            result = {"requestId": request.state.request_id, **payload, "processing": deps.summarize_import_tasks()}
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            deps.cache_put(
                deps.timeline_preview_cache,
                cache_key,
                (now, etag, body),
                ttl=deps.timeline_preview_cache_ttl,
                max_items=deps.body_cache_max,
            )
        total_duration_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
        headers = {
            "ETag": f'"{etag}"',
            "Cache-Control": "no-cache",
            "X-Map-Cache": cache_state,
            "X-Map-Mode": "timeline-preview",
            "Server-Timing": ", ".join(
                [
                    f'cache;desc="{cache_state}"',
                    f"counts;dur={counts_duration_ms:.2f}",
                    f"preview;dur={preview_duration_ms:.2f}",
                    f"serialize;dur={serialize_duration_ms:.2f}",
                    f"total;dur={total_duration_ms:.2f}",
                ]
            ),
        }
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    @app.get("/api/map-meta", dependencies=[Depends(require_admin_access)])
    async def api_map_meta(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> Response:
        request_started_at = time.perf_counter()
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            page=1,
            page_size=1,
        )
        cache_key = str(request.url.query)
        now = time.time()
        cached = deps.cache_get(deps.map_meta_cache, cache_key, ttl=deps.map_meta_cache_ttl)
        cache_state = "miss"
        summary_duration_ms = 0.0
        serialize_duration_ms = 0.0
        if cached:
            _, etag, body = cached
            cache_state = "hit"
        else:
            summary_started_at = time.perf_counter()
            summary = deps.storage(request).summarize_points(filters)
            summary_duration_ms = round((time.perf_counter() - summary_started_at) * 1000, 2)
            result = {
                "requestId": request.state.request_id,
                "meta": summary,
                "processing": deps.summarize_import_tasks(),
            }
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            deps.cache_put(
                deps.map_meta_cache,
                cache_key,
                (now, etag, body),
                ttl=deps.map_meta_cache_ttl,
                max_items=deps.body_cache_max,
            )
        total_duration_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
        headers = {
            "ETag": f'"{etag}"',
            "Cache-Control": "no-cache",
            "X-Map-Cache": cache_state,
            "X-Map-Mode": "meta",
            "Server-Timing": ", ".join(
                [
                    f'cache;desc="{cache_state}"',
                    f"summary;dur={summary_duration_ms:.2f}",
                    f"serialize;dur={serialize_duration_ms:.2f}",
                    f"total;dur={total_duration_ms:.2f}",
                ]
            ),
        }
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    @app.get("/api/map-data", dependencies=[Depends(require_admin_access)])
    async def api_map_data(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        bbox: str | None = Query(default=None),
        page_size: int | None = Query(default=None, ge=1),
        log_limit: int | None = Query(default=None, ge=1),
        latest_known_ts: str | None = Query(default=None),
        zoom: float = Query(default=12, ge=1, le=22),
        route_time_gap_min: int = Query(default=15, ge=1, le=1440),
        route_dist_gap_m: int = Query(default=1200, ge=10, le=50000),
        stop_min_duration_min: int = Query(default=5, ge=1, le=240),
        stop_radius_m: int = Query(default=100, ge=10, le=5000),
        include_points: bool = Query(default=True),
        include_heatmap: bool = Query(default=False),
        include_polyline: bool = Query(default=True),
        include_accuracy: bool = Query(default=False),
        include_labels: bool = Query(default=False),
        include_speed: bool = Query(default=False),
        include_stops: bool = Query(default=False),
        include_daytrack: bool = Query(default=False),
        include_snap: bool = Query(default=False),
    ) -> Response:
        request_started_at = time.perf_counter()
        configured_max = max(1, deps.settings(request).points_page_size_max)
        viewport_bbox = deps.parse_bbox(bbox)
        effective_page_size = min(page_size or configured_max, configured_max, deps.map_data_page_size_max)
        effective_log_limit = min(log_limit or effective_page_size, effective_page_size)
        effective_zoom = max(1, min(22, round(zoom)))
        padded_bbox = deps.expand_bbox(viewport_bbox, zoom=effective_zoom) if viewport_bbox else None
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            page=1,
            page_size=effective_page_size,
        )

        cache_key = str(request.url.query)
        now = time.time()
        cached = deps.cache_get(deps.map_data_cache, cache_key, ttl=deps.map_data_cache_ttl)
        cache_state = "miss"
        latest_check_duration_ms = 0.0
        counts_duration_ms = 0.0
        heatmap_duration_ms = 0.0
        track_context_duration_ms = 0.0
        track_layers_duration_ms = 0.0
        payload_duration_ms = 0.0
        serialize_duration_ms = 0.0
        map_mode = "full"
        if cached:
            _, etag, body = cached
            cache_state = "hit"
            if request.headers.get("if-none-match") == f'"{etag}"':
                return Response(status_code=304, headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache", "X-Map-Cache": "hit"})
        else:
            storage = deps.storage(request)
            delta_mode = False
            if latest_known_ts:
                latest_check_started_at = time.perf_counter()
                latest_visible_ts = storage.latest_point_timestamp(filters, bbox=viewport_bbox, spatial_zoom_hint=effective_zoom)
                latest_visible_dt = deps.parse_iso_timestamp(latest_visible_ts)
                latest_known_dt = deps.parse_iso_timestamp(latest_known_ts)
                latest_check_duration_ms = round((time.perf_counter() - latest_check_started_at) * 1000, 2)
                if latest_visible_dt and latest_known_dt and latest_visible_dt <= latest_known_dt:
                    total_duration_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
                    return Response(
                        status_code=304,
                        headers={
                            "Cache-Control": "no-cache",
                            "X-Map-Delta": "noop",
                            "X-Map-Latest-Ts": latest_visible_ts,
                            "X-Map-Mode": "delta-noop",
                            "X-Map-Cache": "miss",
                            "Server-Timing": f"latest_check;dur={latest_check_duration_ms:.2f}, total;dur={total_duration_ms:.2f}",
                        },
                    )
                delta_mode = True

            viewport_items: list[dict[str, Any]] = []
            visible_points = 0
            total_points = 0
            latest_visible_ts = None
            used_sampled_viewport_items = False
            loaded_layers: list[str] = []
            needs_track_context = include_polyline or include_labels or include_speed or include_stops or include_daytrack or include_snap
            needs_log_points = bool(log_limit and log_limit > 0) and not include_heatmap and not needs_track_context
            needs_viewport_points = include_points or include_accuracy or needs_log_points

            if viewport_bbox:
                counts_started_at = time.perf_counter()
                total_points = storage.count_points(filters)
                visible_points = storage.count_points(filters, bbox=viewport_bbox, spatial_zoom_hint=effective_zoom)

                if needs_viewport_points:
                    target_limit = deps.target_point_limit(effective_zoom, visible_points)
                    if visible_points > target_limit:
                        viewport_items = storage.list_points_in_bbox_sampled(
                            filters,
                            bbox=viewport_bbox,
                            target_limit=target_limit,
                            spatial_zoom_hint=effective_zoom,
                        )
                        used_sampled_viewport_items = True
                    else:
                        viewport_items = storage.list_points_in_bbox(filters, bbox=viewport_bbox, spatial_zoom_hint=effective_zoom)

                counts_duration_ms = round((time.perf_counter() - counts_started_at) * 1000, 2)
            else:
                counts_started_at = time.perf_counter()
                if needs_viewport_points:
                    listed = storage.list_points(filters)
                    total_points = listed["total"]
                    visible_points = len(listed["items"])
                    viewport_items = listed["items"]
                else:
                    total_points = storage.count_points(filters)
                    visible_points = total_points
                counts_duration_ms = round((time.perf_counter() - counts_started_at) * 1000, 2)

            if include_points:
                loaded_layers.append("points")
            if include_accuracy:
                loaded_layers.append("accuracy")

            buffered_items = viewport_items
            delta_viewport_items: list[dict[str, Any]] = []
            delta_polyline_entries: list[dict[str, Any]] = []
            delta_speed_entries: list[dict[str, Any]] = []
            delta_stop_entries: list[dict[str, Any]] = []
            delta_daytrack_entries: list[dict[str, Any]] = []
            delta_snap_entries: list[dict[str, Any]] = []

            if viewport_items:
                latest_visible_ts = viewport_items[0]["point_timestamp_utc"]
            if latest_known_ts:
                latest_known_dt = deps.parse_iso_timestamp(latest_known_ts)
                if latest_known_dt:
                    map_mode = "delta"
                    normalized_since = latest_known_dt.astimezone(timezone.utc).isoformat()
                    delta_viewport_items = storage.list_points_since(
                        filters,
                        since_utc=normalized_since,
                        bbox=viewport_bbox,
                        spatial_zoom_hint=effective_zoom,
                    )
            heatmap_entries = []
            if include_heatmap:
                heatmap_started_at = time.perf_counter()
                bucketed_bbox = deps.bucket_bbox_for_zoom(viewport_bbox, zoom=effective_zoom)
                heatmap_entries = deps.resolve_heatmap_layer(
                    storage,
                    filters,
                    bbox=bucketed_bbox or viewport_bbox,
                    zoom=effective_zoom,
                )
                heatmap_duration_ms = round((time.perf_counter() - heatmap_started_at) * 1000, 2)
                loaded_layers.append("heatmap")

            track_layers = {
                "polylines": [],
                "speed": [],
                "stops": [],
                "daytracks": [],
                "snap": [],
                "context_points_desc": viewport_items,
                "segment_count": 0,
            }
            defer_expensive_track_layers = delta_mode and len(delta_viewport_items) <= 24
            if needs_track_context:
                preloaded_track_points = None
                if not used_sampled_viewport_items:
                    if not viewport_bbox or padded_bbox == viewport_bbox:
                        preloaded_track_points = viewport_items

                track_context_started_at = time.perf_counter()
                track_context = await asyncio.to_thread(
                    deps.resolve_track_context,
                    storage,
                    filters,
                    bbox=padded_bbox or viewport_bbox,
                    zoom=effective_zoom,
                    route_time_gap_min=route_time_gap_min,
                    route_dist_gap_m=route_dist_gap_m,
                    preloaded_points_desc=preloaded_track_points,
                )
                track_context_duration_ms = round((time.perf_counter() - track_context_started_at) * 1000, 2)
                track_layers_started_at = time.perf_counter()
                track_layers = await asyncio.to_thread(
                    deps.resolve_track_layers,
                    track_context,
                    zoom=effective_zoom,
                    include_polyline=include_polyline,
                    include_labels=include_labels,
                    include_speed=include_speed and not defer_expensive_track_layers,
                    include_stops=include_stops and not defer_expensive_track_layers,
                    stop_min_duration_min=stop_min_duration_min,
                    stop_radius_m=stop_radius_m,
                    include_daytrack=include_daytrack and not defer_expensive_track_layers,
                    route_time_gap_min=route_time_gap_min,
                    include_snap=include_snap and not delta_mode,
                )
                if include_polyline:
                    loaded_layers.append("polyline")
                if include_labels:
                    loaded_layers.append("labels")
                if include_speed and not defer_expensive_track_layers:
                    loaded_layers.append("speed")
                if include_stops and not defer_expensive_track_layers:
                    loaded_layers.append("stops")
                if include_daytrack and not defer_expensive_track_layers:
                    loaded_layers.append("daytrack")
                if include_snap and not delta_mode:
                    loaded_layers.append("snap")
                if not viewport_bbox and filters.session_id:
                    if include_stops:
                        precomputed_stops = storage.list_precomputed_session_stops(
                            filters,
                            stop_radius_m=stop_radius_m,
                            stop_min_duration_min=stop_min_duration_min,
                        )
                        if precomputed_stops is not None:
                            track_layers["stops"] = precomputed_stops
                    if include_daytrack:
                        precomputed_daytracks = storage.list_precomputed_session_daytracks(
                            filters,
                            zoom=effective_zoom,
                            route_time_gap_min=route_time_gap_min,
                        )
                        if precomputed_daytracks is not None:
                            track_layers["daytracks"] = precomputed_daytracks
                track_layers_duration_ms = round((time.perf_counter() - track_layers_started_at) * 1000, 2)
                buffered_items = track_layers["context_points_desc"]
                if delta_mode and delta_viewport_items:
                    delta_anchor_points_desc = track_layers["context_points_desc"] if used_sampled_viewport_items else viewport_items
                    delta_context_points_asc = deps.build_delta_context_points_asc(delta_anchor_points_desc, delta_viewport_items)
                    if delta_context_points_asc:
                        delta_segments = deps.segment_track(
                            delta_context_points_asc,
                            time_gap_ms=route_time_gap_min * 60000,
                            dist_gap_m=route_dist_gap_m,
                        )
                        if include_polyline or include_labels:
                            delta_polyline_entries = deps.serialize_polyline_segments(
                                delta_segments,
                                zoom=effective_zoom,
                                include_labels=include_labels,
                            )
                        if include_speed:
                            delta_speed_entries = deps.serialize_speed_segments(delta_context_points_asc, zoom=effective_zoom)
                        if include_stops:
                            if defer_expensive_track_layers:
                                delta_stop_entries = deps.detect_stops(
                                    delta_context_points_asc,
                                    stop_radius_m=stop_radius_m,
                                    stop_min_duration_min=stop_min_duration_min,
                                )
                            else:
                                min_delta_ts = min(str(point["point_timestamp_utc"]) for point in delta_viewport_items)
                                delta_stop_entries = [
                                    item
                                    for item in track_layers["stops"]
                                    if str(item.get("endTimeUtc") or "") >= min_delta_ts or str(item.get("startTimeUtc") or "") >= min_delta_ts
                                ]
                        if include_daytrack and not defer_expensive_track_layers:
                            affected_days = {str(point["point_date_local"]) for point in delta_viewport_items}
                            delta_daytrack_entries = [
                                item for item in track_layers["daytracks"] if str(item.get("day") or "") in affected_days
                            ]
                        if include_snap and len(delta_context_points_asc) <= 8 and len(delta_segments) <= 2:
                            delta_snap_entries = deps.serialize_snap_segments(
                                delta_segments,
                                zoom=effective_zoom,
                                allow_network=False,
                            )
                        if delta_speed_entries and "speed" not in loaded_layers:
                            loaded_layers.append("speed")
                        if delta_stop_entries and "stops" not in loaded_layers:
                            loaded_layers.append("stops")
                        if delta_snap_entries and "snap" not in loaded_layers:
                            loaded_layers.append("snap")
            if delta_mode:
                payload_started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    deps.prepare_map_delta_payload,
                    viewport_items,
                    delta_viewport_items,
                    buffered_items,
                    heatmap_entries=heatmap_entries,
                    polyline_entries=track_layers["polylines"],
                    delta_polyline_entries=delta_polyline_entries,
                    speed_entries=track_layers["speed"],
                    delta_speed_entries=delta_speed_entries,
                    stop_entries=track_layers["stops"],
                    delta_stop_entries=delta_stop_entries,
                    daytrack_entries=track_layers["daytracks"],
                    delta_daytrack_entries=delta_daytrack_entries,
                    snap_entries=track_layers["snap"],
                    delta_snap_entries=delta_snap_entries,
                    total_points=total_points,
                    visible_points=visible_points,
                    segment_count=int(track_layers["segment_count"]),
                    log_limit=effective_log_limit,
                    include_points=include_points,
                    include_heatmap=include_heatmap,
                    include_accuracy=include_accuracy,
                    include_speed=include_speed and (not defer_expensive_track_layers or bool(delta_speed_entries)),
                    include_stops=include_stops and (not defer_expensive_track_layers or bool(delta_stop_entries)),
                    include_daytrack=include_daytrack and not defer_expensive_track_layers,
                    include_snap=include_snap and bool(delta_snap_entries),
                    loaded_layers=loaded_layers,
                )
                payload_duration_ms = round((time.perf_counter() - payload_started_at) * 1000, 2)
            else:
                payload_started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    deps.prepare_map_payload,
                    viewport_items,
                    buffered_items,
                    heatmap_entries=heatmap_entries,
                    polyline_entries=track_layers["polylines"],
                    speed_entries=track_layers["speed"],
                    stop_entries=track_layers["stops"],
                    daytrack_entries=track_layers["daytracks"],
                    snap_entries=track_layers["snap"],
                    total_points=total_points,
                    visible_points=visible_points,
                    segment_count=int(track_layers["segment_count"]),
                    log_limit=effective_log_limit,
                    zoom=effective_zoom,
                    include_points=include_points,
                    include_heatmap=include_heatmap,
                    include_accuracy=include_accuracy,
                    loaded_layers=loaded_layers,
                )
                payload_duration_ms = round((time.perf_counter() - payload_started_at) * 1000, 2)
            if viewport_bbox:
                payload["meta"]["bbox"] = {
                    "minLon": viewport_bbox[0],
                    "minLat": viewport_bbox[1],
                    "maxLon": viewport_bbox[2],
                    "maxLat": viewport_bbox[3],
                }
            payload["meta"]["latestVisiblePointTsUtc"] = latest_visible_ts
            result = {"requestId": request.state.request_id, **payload}
            result["processing"] = deps.summarize_import_tasks()
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            deps.cache_put(
                deps.map_data_cache,
                cache_key,
                (now, etag, body),
                ttl=deps.map_data_cache_ttl,
                max_items=deps.body_cache_max,
            )
        total_duration_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
        headers = {
            "ETag": f'"{etag}"',
            "Cache-Control": "no-cache",
            "X-Map-Cache": cache_state,
            "X-Map-Mode": map_mode,
            "Server-Timing": ", ".join(
                [
                    f'cache;desc="{cache_state}"',
                    f"latest_check;dur={latest_check_duration_ms:.2f}",
                    f"counts;dur={counts_duration_ms:.2f}",
                    f"heatmap;dur={heatmap_duration_ms:.2f}",
                    f"track_context;dur={track_context_duration_ms:.2f}",
                    f"track_layers;dur={track_layers_duration_ms:.2f}",
                    f"payload;dur={payload_duration_ms:.2f}",
                    f"serialize;dur={serialize_duration_ms:.2f}",
                    f"total;dur={total_duration_ms:.2f}",
                ]
            ),
        }
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)
