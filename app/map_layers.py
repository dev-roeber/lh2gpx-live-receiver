from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable
from urllib.request import urlopen

from .map_payloads import (
    _aggregate_heatmap,
    _bucket_bbox_for_zoom,
    _detect_stops,
    _downsample_points,
    _parse_iso_timestamp,
    _point_dt,
    _segment_track,
    _serialize_daytracks,
    _serialize_speed_segments,
    _simplify_segment,
)
from .models import PointFilters
from .storage import ReceiverStorage


def serialize_polyline_segments(
    segments: list[list[dict[str, Any]]],
    *,
    zoom: int,
    include_labels: bool,
    snap_segment_fn: Callable[..., list[list[float]] | None],
    palette_color_fn: Callable[[int], str],
) -> list[dict[str, Any]]:
    serialized = []
    for index, segment in enumerate(segments):
        coords = snap_segment_fn(segment, zoom=zoom) or _simplify_segment(segment, zoom)
        serialized.append(
            {
                "color": palette_color_fn(index),
                "coords": coords,
                "pointsCount": len(segment),
                "startLabel": (segment[0]["point_timestamp_local"] or "")[11:16] if include_labels else "",
                "endLabel": (segment[-1]["point_timestamp_local"] or "")[11:16] if include_labels else "",
                "startPoint": coords[0] if coords else [float(segment[0]["latitude"]), float(segment[0]["longitude"])],
                "endPoint": coords[-1] if coords else [float(segment[-1]["latitude"]), float(segment[-1]["longitude"])],
            }
        )
    return serialized


def resolve_heatmap_layer(
    storage: ReceiverStorage,
    filters: PointFilters,
    *,
    bbox: tuple[float, float, float, float] | None,
    zoom: int,
    heatmap_cache: dict[str, tuple[float, list[list[float]]]],
    heatmap_cache_ttl: float,
    layer_cache_max: int,
    cache_get_fn: Callable[..., tuple[Any, ...] | None],
    cache_put_fn: Callable[..., None],
) -> list[list[float]]:
    bucketed_bbox = _bucket_bbox_for_zoom(bbox, zoom=zoom)
    cache_key = json.dumps(
        {
            "date_from": filters.date_from,
            "date_to": filters.date_to,
            "session_id": filters.session_id,
            "capture_mode": filters.capture_mode,
            "source": filters.source,
            "search": filters.search,
            "zoom": zoom,
            "bbox": bucketed_bbox,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cached = cache_get_fn(heatmap_cache, cache_key, ttl=heatmap_cache_ttl)
    if cached:
        return cached[1]

    now = time.time()
    rows = storage.list_heatmap_points(filters, bbox=bucketed_bbox or bbox, spatial_zoom_hint=zoom)
    result = _aggregate_heatmap(rows, zoom=zoom)
    cache_put_fn(heatmap_cache, cache_key, (now, result), ttl=heatmap_cache_ttl, max_items=layer_cache_max)
    return result


def resolve_track_context(
    storage: ReceiverStorage,
    filters: PointFilters,
    *,
    bbox: tuple[float, float, float, float] | None,
    zoom: int,
    route_time_gap_min: int,
    route_dist_gap_m: int,
    preloaded_points_desc: list[dict[str, Any]] | None,
    track_context_cache: dict[str, tuple[float, dict[str, Any]]],
    track_context_cache_ttl: float,
    layer_cache_max: int,
    cache_get_fn: Callable[..., tuple[Any, ...] | None],
    cache_put_fn: Callable[..., None],
) -> dict[str, Any]:
    bucketed_bbox = _bucket_bbox_for_zoom(bbox, zoom=zoom)
    cache_key = json.dumps(
        {
            "date_from": filters.date_from,
            "date_to": filters.date_to,
            "session_id": filters.session_id,
            "capture_mode": filters.capture_mode,
            "source": filters.source,
            "search": filters.search,
            "zoom": zoom,
            "bbox": bucketed_bbox,
            "route_time_gap_min": route_time_gap_min,
            "route_dist_gap_m": route_dist_gap_m,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cached = cache_get_fn(track_context_cache, cache_key, ttl=track_context_cache_ttl)
    if cached:
        return cached[1]

    now = time.time()
    if preloaded_points_desc is not None:
        points_desc = preloaded_points_desc
    elif bbox:
        points_desc = storage.list_points_in_bbox(filters, bbox=bbox, spatial_zoom_hint=zoom)
    else:
        points_desc = storage.list_points(filters)["items"]
    points_asc = list(reversed(points_desc))
    segments = _segment_track(
        points_asc,
        time_gap_ms=route_time_gap_min * 60000,
        dist_gap_m=route_dist_gap_m,
    )
    context = {
        "cache_key": cache_key,
        "points_desc": points_desc,
        "points_asc": points_asc,
        "segments": segments,
    }
    cache_put_fn(track_context_cache, cache_key, (now, context), ttl=track_context_cache_ttl, max_items=layer_cache_max)
    return context


def resolve_track_layers(
    track_context: dict[str, Any],
    *,
    zoom: int,
    include_polyline: bool,
    include_labels: bool,
    include_speed: bool,
    include_stops: bool,
    stop_min_duration_min: int,
    stop_radius_m: int,
    include_daytrack: bool,
    route_time_gap_min: int,
    include_snap: bool,
    track_layer_cache: dict[str, tuple[float, dict[str, Any]]],
    track_layer_cache_ttl: float,
    layer_cache_max: int,
    cache_get_fn: Callable[..., tuple[Any, ...] | None],
    cache_put_fn: Callable[..., None],
    serialize_polyline_segments_fn: Callable[..., list[dict[str, Any]]],
    serialize_snap_segments_fn: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    cache_key = json.dumps(
        {
            "context": track_context["cache_key"],
            "zoom": zoom,
            "include_polyline": include_polyline,
            "include_labels": include_labels,
            "include_speed": include_speed,
            "include_stops": include_stops,
            "stop_min_duration_min": stop_min_duration_min,
            "stop_radius_m": stop_radius_m,
            "include_daytrack": include_daytrack,
            "route_time_gap_min": route_time_gap_min,
            "include_snap": include_snap,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cached = cache_get_fn(track_layer_cache, cache_key, ttl=track_layer_cache_ttl)
    if cached:
        return cached[1]

    now = time.time()
    points_desc = track_context["points_desc"]
    points_asc = track_context["points_asc"]
    segments = track_context["segments"]
    result = {
        "context_points_desc": points_desc,
        "segment_count": len(segments),
        "polylines": serialize_polyline_segments_fn(segments, zoom=zoom, include_labels=include_labels)
        if (include_polyline or include_labels)
        else [],
        "speed": _serialize_speed_segments(points_asc, zoom=zoom) if include_speed else [],
        "stops": _detect_stops(
            points_asc,
            stop_radius_m=stop_radius_m,
            stop_min_duration_min=stop_min_duration_min,
        )
        if include_stops
        else [],
        "daytracks": _serialize_daytracks(
            points_asc,
            zoom=zoom,
            route_time_gap_min=route_time_gap_min,
        )
        if include_daytrack
        else [],
        "snap": serialize_snap_segments_fn(segments, zoom=zoom) if include_snap else [],
    }
    cache_put_fn(track_layer_cache, cache_key, (now, result), ttl=track_layer_cache_ttl, max_items=layer_cache_max)
    return result


def serialize_snap_segments(
    segments: list[list[dict[str, Any]]],
    *,
    zoom: int,
    allow_network: bool,
    snap_segment_fn: Callable[..., list[list[float]] | None],
) -> list[dict[str, Any]]:
    snapped = []
    for segment in segments[:10]:
        coords = snap_segment_fn(segment, zoom=zoom, allow_network=allow_network)
        if coords:
            snapped.append({"coords": coords})
    return snapped


def snap_segment(
    segment: list[dict[str, Any]],
    *,
    zoom: int,
    allow_network: bool,
    snap_cache: dict[str, tuple[float, list[list[float]] | None]],
    snap_cache_ttl: float,
    snap_cache_max: int,
    cache_get_fn: Callable[..., tuple[Any, ...] | None],
    cache_put_fn: Callable[..., None],
) -> list[list[float]] | None:
    sampled = _downsample_points(segment, 80 if zoom <= 14 else 120)
    if len(sampled) < 2:
        return None
    key = hashlib.sha1(
        "|".join(
            f"{point['point_timestamp_utc']}:{float(point['latitude']):.6f}:{float(point['longitude']):.6f}"
            for point in sampled
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()
    cached = cache_get_fn(snap_cache, key, ttl=snap_cache_ttl)
    if cached:
        return cached[1]
    if not allow_network:
        return None
    now = time.time()
    coords = ";".join(f"{float(point['longitude']):.6f},{float(point['latitude']):.6f}" for point in sampled)
    timestamps = [int(_point_dt(point).timestamp()) for point in sampled]
    for index in range(1, len(timestamps)):
        if timestamps[index] <= timestamps[index - 1]:
            timestamps[index] = timestamps[index - 1] + 1
    url = (
        "https://router.project-osrm.org/match/v1/driving/"
        f"{coords}?overview=full&geometries=geojson&timestamps={';'.join(str(value) for value in timestamps)}"
        f"&radiuses={';'.join('50' for _ in sampled)}"
    )
    try:
        with urlopen(url, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("code") != "Ok" or not payload.get("matchings"):
            result = None
        else:
            result = [
                [round(lat, 6), round(lon, 6)]
                for matching in payload["matchings"]
                for lon, lat in matching["geometry"]["coordinates"]
            ]
    except Exception:
        result = None
    cache_put_fn(snap_cache, key, (now, result), ttl=snap_cache_ttl, max_items=snap_cache_max)
    return result
