from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable


def _prepare_map_payload(
    viewport_points_desc: list[dict[str, Any]],
    buffered_points_desc: list[dict[str, Any]],
    *,
    heatmap_entries: list[list[float]],
    polyline_entries: list[dict[str, Any]],
    speed_entries: list[dict[str, Any]],
    stop_entries: list[dict[str, Any]],
    daytrack_entries: list[dict[str, Any]],
    snap_entries: list[dict[str, Any]],
    total_points: int,
    visible_points: int,
    segment_count: int,
    log_limit: int,
    zoom: int,
    include_points: bool,
    include_heatmap: bool,
    include_accuracy: bool,
    loaded_layers: list[str] | None = None,
) -> dict[str, Any]:
    if not buffered_points_desc:
        return {
            "meta": {
                "totalPoints": total_points,
                "visiblePoints": visible_points,
                "loadedPoints": 0,
                "serverPrepared": True,
                "loadedLayers": loaded_layers or [],
            },
            "stats": {"pointsPerMinute": 0, "avgAccuracyM": None, "sessionDurationSeconds": 0},
            "layers": {
                "points": [],
                "latestPoint": None,
                "heatmap": heatmap_entries if include_heatmap else [],
                "polylines": [],
                "accuracy": [],
                "speed": [],
                "stops": [],
                "daytracks": [],
                "snap": [],
            },
            "logItems": [],
        }

    visible_points_desc = viewport_points_desc
    stats_points_desc = visible_points_desc or buffered_points_desc
    sorted_points = list(reversed(buffered_points_desc))
    latest = stats_points_desc[0]
    avg_accuracy = sum(float(point["horizontal_accuracy_m"]) for point in stats_points_desc) / len(stats_points_desc)

    payload = {
        "meta": {
            "totalPoints": total_points,
            "visiblePoints": visible_points,
            "loadedPoints": len(buffered_points_desc),
            "serverPrepared": True,
            "segmentCount": segment_count,
            "loadedLayers": loaded_layers or [],
        },
        "stats": {
            "pointsPerMinute": _points_per_minute(stats_points_desc),
            "avgAccuracyM": round(avg_accuracy, 2),
            "sessionDurationSeconds": _track_duration_seconds(sorted_points),
        },
        "layers": {
            "points": [],
            "latestPoint": _serialize_latest_point(latest) if include_points else None,
            "heatmap": [],
            "polylines": [],
            "accuracy": [],
            "speed": [],
            "stops": [],
            "daytracks": [],
            "snap": [],
        },
        "logItems": [_serialize_log_point(point) for point in stats_points_desc[:max(1, log_limit)]],
    }

    if include_points:
        viewport_sorted_points = list(reversed(visible_points_desc))
        sampled_points = _downsample_points(viewport_sorted_points, _target_point_limit(zoom, len(viewport_sorted_points)))
        payload["layers"]["points"] = [_serialize_map_point(point, latest["id"]) for point in sampled_points]

    if include_heatmap:
        payload["layers"]["heatmap"] = heatmap_entries

    payload["layers"]["polylines"] = polyline_entries

    if include_accuracy:
        payload["layers"]["accuracy"] = _serialize_accuracy_entries(visible_points_desc)

    payload["layers"]["speed"] = speed_entries
    payload["layers"]["stops"] = stop_entries
    payload["layers"]["daytracks"] = daytrack_entries
    payload["layers"]["snap"] = snap_entries

    return payload


def _serialize_accuracy_entries(points_desc: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"lat": point["latitude"], "lon": point["longitude"], "radius": point["horizontal_accuracy_m"]}
        for point in _downsample_points(list(reversed(points_desc)), 300)
        if 0 < float(point["horizontal_accuracy_m"]) < 5000
    ]


def _prepare_map_delta_payload(
    current_viewport_points_desc: list[dict[str, Any]],
    new_viewport_points_desc: list[dict[str, Any]],
    buffered_points_desc: list[dict[str, Any]],
    *,
    heatmap_entries: list[list[float]],
    polyline_entries: list[dict[str, Any]],
    delta_polyline_entries: list[dict[str, Any]],
    speed_entries: list[dict[str, Any]],
    delta_speed_entries: list[dict[str, Any]],
    stop_entries: list[dict[str, Any]],
    delta_stop_entries: list[dict[str, Any]],
    daytrack_entries: list[dict[str, Any]],
    delta_daytrack_entries: list[dict[str, Any]],
    snap_entries: list[dict[str, Any]],
    delta_snap_entries: list[dict[str, Any]],
    total_points: int,
    visible_points: int,
    segment_count: int,
    log_limit: int,
    include_points: bool,
    include_heatmap: bool,
    include_accuracy: bool,
    include_speed: bool,
    include_stops: bool,
    include_daytrack: bool,
    include_snap: bool,
    loaded_layers: list[str] | None = None,
) -> dict[str, Any]:
    stats_points_desc = current_viewport_points_desc or buffered_points_desc
    latest = stats_points_desc[0] if stats_points_desc else None
    sorted_points = list(reversed(buffered_points_desc))
    avg_accuracy = (
        sum(float(point["horizontal_accuracy_m"]) for point in stats_points_desc) / len(stats_points_desc)
        if stats_points_desc
        else None
    )
    payload = {
        "meta": {
            "totalPoints": total_points,
            "visiblePoints": visible_points,
            "loadedPoints": len(buffered_points_desc),
            "serverPrepared": True,
            "segmentCount": segment_count,
            "deltaMode": True,
            "latestVisiblePointTsUtc": latest["point_timestamp_utc"] if latest else None,
            "loadedLayers": loaded_layers or [],
        },
        "stats": {
            "pointsPerMinute": _points_per_minute(stats_points_desc) if stats_points_desc else 0,
            "avgAccuracyM": round(avg_accuracy, 2) if avg_accuracy is not None else None,
            "sessionDurationSeconds": _track_duration_seconds(sorted_points),
        },
        "delta": {
            "appendPoints": [],
            "latestPoint": _serialize_latest_point(latest) if (latest and include_points) else None,
            "appendLogItems": [_serialize_log_point(point) for point in new_viewport_points_desc[:max(1, log_limit)]],
        },
    }
    if include_points:
        latest_id = int(latest["id"]) if latest else -1
        payload["delta"]["appendPoints"] = [
            _serialize_map_point(point, latest_id) for point in list(reversed(new_viewport_points_desc))
        ]
    if include_heatmap:
        payload["delta"]["replaceHeatmap"] = heatmap_entries
    if delta_polyline_entries:
        payload["delta"]["appendPolylines"] = delta_polyline_entries
    else:
        payload["delta"]["replacePolylines"] = polyline_entries
    if include_accuracy:
        payload["delta"]["replaceAccuracy"] = _serialize_accuracy_entries(current_viewport_points_desc)
    if include_speed:
        if delta_speed_entries:
            payload["delta"]["appendSpeed"] = delta_speed_entries
        else:
            payload["delta"]["replaceSpeed"] = speed_entries
    if include_stops:
        if delta_stop_entries:
            payload["delta"]["upsertStops"] = delta_stop_entries
        else:
            payload["delta"]["replaceStops"] = stop_entries
    if include_daytrack:
        if delta_daytrack_entries:
            payload["delta"]["upsertDaytracks"] = delta_daytrack_entries
        else:
            payload["delta"]["replaceDaytracks"] = daytrack_entries
    if include_snap:
        if delta_snap_entries:
            payload["delta"]["appendSnap"] = delta_snap_entries
        elif snap_entries:
            payload["delta"]["replaceSnap"] = snap_entries
    return payload


def _build_delta_context_points_asc(
    current_viewport_points_desc: list[dict[str, Any]],
    new_viewport_points_desc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not new_viewport_points_desc:
        return []
    new_ids = {int(point["id"]) for point in new_viewport_points_desc}
    old_anchor = next(
        (point for point in current_viewport_points_desc if int(point["id"]) not in new_ids),
        None,
    )
    points_asc = list(reversed(new_viewport_points_desc))
    if old_anchor is not None:
        points_asc = [old_anchor, *points_asc]
    return points_asc


def _prepare_timeline_preview_payload(
    viewport_points_desc: list[dict[str, Any]],
    *,
    total_points: int,
    visible_points: int,
    log_limit: int,
    zoom: int,
    include_points: bool,
    include_accuracy: bool,
    include_polyline: bool,
    include_labels: bool,
    route_time_gap_min: int,
    route_dist_gap_m: int,
    serialize_polyline_segments_fn: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    if not viewport_points_desc:
        return {
            "meta": {
                "totalPoints": total_points,
                "visiblePoints": visible_points,
                "loadedPoints": 0,
                "serverPrepared": True,
                "previewMode": "timeline",
            },
            "stats": {"pointsPerMinute": 0, "avgAccuracyM": None, "sessionDurationSeconds": 0},
            "layers": {
                "points": [],
                "latestPoint": None,
                "heatmap": [],
                "polylines": [],
                "accuracy": [],
                "speed": [],
                "stops": [],
                "daytracks": [],
                "snap": [],
            },
            "logItems": [],
        }

    points_asc = list(reversed(viewport_points_desc))
    latest = viewport_points_desc[0]
    avg_accuracy = sum(float(point["horizontal_accuracy_m"]) for point in viewport_points_desc) / len(viewport_points_desc)
    segments = _segment_track(
        points_asc,
        time_gap_ms=route_time_gap_min * 60000,
        dist_gap_m=route_dist_gap_m,
    )
    payload = {
        "meta": {
            "totalPoints": total_points,
            "visiblePoints": visible_points,
            "loadedPoints": len(viewport_points_desc),
            "serverPrepared": True,
            "segmentCount": len(segments),
            "previewMode": "timeline",
            "latestVisiblePointTsUtc": latest["point_timestamp_utc"],
        },
        "stats": {
            "pointsPerMinute": _points_per_minute(viewport_points_desc),
            "avgAccuracyM": round(avg_accuracy, 2),
            "sessionDurationSeconds": _track_duration_seconds(points_asc),
        },
        "layers": {
            "points": [],
            "latestPoint": _serialize_latest_point(latest) if include_points else None,
            "heatmap": [],
            "polylines": serialize_polyline_segments_fn(segments, zoom=zoom, include_labels=include_labels)
            if include_polyline
            else [],
            "accuracy": _serialize_accuracy_entries(viewport_points_desc) if include_accuracy else [],
            "speed": [],
            "stops": [],
            "daytracks": [],
            "snap": [],
        },
        "logItems": [_serialize_log_point(point) for point in viewport_points_desc[:max(1, log_limit)]],
    }
    if include_points:
        sampled_points = _downsample_points(points_asc, _target_point_limit(zoom, len(points_asc)))
        payload["layers"]["points"] = [_serialize_map_point(point, latest["id"]) for point in sampled_points]
    return payload


def _point_dt(point: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(point["point_timestamp_utc"]))


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace(" ", "+")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _track_duration_seconds(points_asc: list[dict[str, Any]]) -> int:
    if len(points_asc) < 2:
        return 0
    return max(0, int((_point_dt(points_asc[-1]) - _point_dt(points_asc[0])).total_seconds()))


def _points_per_minute(points_desc: list[dict[str, Any]]) -> float:
    if len(points_desc) < 2:
        return 0.0
    recent = points_desc[: min(100, len(points_desc))]
    newest = _point_dt(recent[0])
    oldest = _point_dt(recent[-1])
    elapsed_minutes = max((newest - oldest).total_seconds() / 60, 0.0001)
    return round(len(recent) / elapsed_minutes, 2)


def _target_point_limit(zoom: int, available: int) -> int:
    if zoom <= 8:
        target = 140
    elif zoom <= 10:
        target = 220
    elif zoom <= 12:
        target = 360
    elif zoom <= 14:
        target = 700
    elif zoom <= 16:
        target = 1200
    else:
        target = 2000
    return max(2, min(available, target))


def _downsample_points(points_asc: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(points_asc) <= limit:
        return points_asc
    if limit <= 2:
        return [points_asc[0], points_asc[-1]]
    stride = (len(points_asc) - 1) / (limit - 1)
    sampled = []
    seen: set[int] = set()
    for index in range(limit):
        source_index = min(len(points_asc) - 1, round(index * stride))
        point = points_asc[source_index]
        point_id = int(point["id"])
        if point_id in seen:
            continue
        sampled.append(point)
        seen.add(point_id)
    if sampled[-1]["id"] != points_asc[-1]["id"]:
        sampled[-1] = points_asc[-1]
    return sampled


def _haversine_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius = 6371000.0
    lat1 = math.radians(float(a["latitude"]))
    lon1 = math.radians(float(a["longitude"]))
    lat2 = math.radians(float(b["latitude"]))
    lon2 = math.radians(float(b["longitude"]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    root = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(root))


def _segment_track(points_asc: list[dict[str, Any]], *, time_gap_ms: int, dist_gap_m: int) -> list[list[dict[str, Any]]]:
    if len(points_asc) < 2:
        return []
    segments: list[list[dict[str, Any]]] = []
    segment = [points_asc[0]]
    hard_jump_dist_m = max(dist_gap_m * 8, 15000)
    hard_jump_speed_kmh = 220.0
    for current in points_asc[1:]:
        previous = segment[-1]
        time_gap = (_point_dt(current) - _point_dt(previous)).total_seconds() * 1000
        dist_gap = _haversine_m(previous, current)
        elapsed_seconds = max(time_gap / 1000, 0.001)
        implied_speed_kmh = (dist_gap / elapsed_seconds) * 3.6
        split_for_distance = dist_gap >= hard_jump_dist_m or (dist_gap > dist_gap_m and implied_speed_kmh > hard_jump_speed_kmh)
        if time_gap > time_gap_ms or split_for_distance:
            if len(segment) > 1:
                segments.append(segment)
            segment = [current]
            continue
        segment.append(current)
    if len(segment) > 1:
        segments.append(segment)
    return _compact_track_segments(segments, time_gap_ms=time_gap_ms, dist_gap_m=dist_gap_m)


def _segment_duration_ms(segment: list[dict[str, Any]]) -> float:
    if len(segment) < 2:
        return 0.0
    return (_point_dt(segment[-1]) - _point_dt(segment[0])).total_seconds() * 1000


def _is_micro_segment(segment: list[dict[str, Any]], *, time_gap_ms: int) -> bool:
    return len(segment) <= 6 or _segment_duration_ms(segment) <= max(180000, time_gap_ms * 0.6)


def _compact_track_segments(
    segments: list[list[dict[str, Any]]],
    *,
    time_gap_ms: int,
    dist_gap_m: int,
) -> list[list[dict[str, Any]]]:
    if len(segments) <= 1:
        return segments
    soft_time_gap_ms = max(time_gap_ms * 3, 15 * 60000)
    soft_dist_gap_m = max(dist_gap_m * 4, 1200)
    hard_time_gap_ms = max(time_gap_ms * 12, 2 * 3600 * 1000)
    hard_dist_gap_m = max(dist_gap_m * 10, 10000)
    compacted = [segments[0]]
    for segment in segments[1:]:
        previous = compacted[-1]
        gap_time_ms = (_point_dt(segment[0]) - _point_dt(previous[-1])).total_seconds() * 1000
        gap_dist_m = _haversine_m(previous[-1], segment[0])
        should_merge = (
            gap_time_ms <= soft_time_gap_ms
            and gap_dist_m <= soft_dist_gap_m
            and (gap_time_ms < hard_time_gap_ms and gap_dist_m < hard_dist_gap_m)
            and (_is_micro_segment(previous, time_gap_ms=time_gap_ms) or _is_micro_segment(segment, time_gap_ms=time_gap_ms))
        )
        if should_merge:
            previous.extend(segment)
            continue
        compacted.append(segment)
    return compacted


def _rdp(coords: list[list[float]], epsilon: float) -> list[list[float]]:
    if len(coords) <= 2 or epsilon <= 0:
        return coords
    start = coords[0]
    end = coords[-1]
    x1, y1 = start
    x2, y2 = end
    denominator = math.hypot(x2 - x1, y2 - y1)
    max_distance = -1.0
    split_index = -1
    for index in range(1, len(coords) - 1):
        x0, y0 = coords[index]
        if denominator == 0:
            distance = math.hypot(x0 - x1, y0 - y1)
        else:
            distance = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / denominator
        if distance > max_distance:
            max_distance = distance
            split_index = index
    if max_distance <= epsilon or split_index < 0:
        return [start, end]
    left = _rdp(coords[: split_index + 1], epsilon)
    right = _rdp(coords[split_index:], epsilon)
    return left[:-1] + right


def _simplify_segment(segment: list[dict[str, Any]], zoom: int) -> list[list[float]]:
    coords = [[float(point["latitude"]), float(point["longitude"])] for point in segment]
    if len(coords) <= 2:
        return coords
    tolerance_m = 120 if zoom <= 8 else 60 if zoom <= 10 else 25 if zoom <= 12 else 10 if zoom <= 14 else 4 if zoom <= 16 else 1
    epsilon = tolerance_m / 111320.0
    return _rdp(coords, epsilon)


def _palette_color(index: int) -> str:
    palette = ["#0A84FF", "#30D158", "#FF9F0A", "#BF5AF2", "#5AC8FA", "#FF453A", "#FFD60A", "#64D2FF"]
    return palette[index % len(palette)]


def _speed_color(kmh: float) -> str:
    normalized_kmh = max(0.0, kmh)
    if normalized_kmh <= 100.0:
        normalized_kmh = min(100.0, round(normalized_kmh / 5.0) * 5.0)
    hue = round(240 - min(300.0, normalized_kmh) / 300.0 * 240)
    lightness = 55 if kmh < 10 else 50 if kmh > 250 else 52
    return f"hsl({hue},95%,{lightness}%)"


def _serialize_speed_segments(points_asc: list[dict[str, Any]], *, zoom: int) -> list[dict[str, Any]]:
    sampled = _downsample_points(points_asc, _target_point_limit(zoom, len(points_asc)))
    segments = []
    for previous, current in zip(sampled, sampled[1:], strict=False):
        seconds = max((_point_dt(current) - _point_dt(previous)).total_seconds(), 0.0)
        if seconds <= 0:
            continue
        kmh = (_haversine_m(previous, current) / seconds) * 3.6
        if kmh > 500:
            continue
        segments.append(
            {
                "coords": [
                    [float(previous["latitude"]), float(previous["longitude"])],
                    [float(current["latitude"]), float(current["longitude"])],
                ],
                "kmh": round(kmh, 1),
                "color": _speed_color(kmh),
            }
        )
    return segments


def _heat_cell_m(zoom: int) -> int:
    return 800 if zoom <= 8 else 350 if zoom <= 10 else 160 if zoom <= 12 else 80 if zoom <= 14 else 40 if zoom <= 16 else 20


def _aggregate_heatmap(points_desc: list[dict[str, Any]], *, zoom: int) -> list[list[float]]:
    cell_m = _heat_cell_m(zoom)
    lat_step = cell_m / 111320.0
    buckets: dict[tuple[int, int], dict[str, float]] = {}
    for point in points_desc:
        lat = float(point["latitude"])
        lon = float(point["longitude"])
        lon_step = max(lat_step / max(math.cos(math.radians(lat)), 0.2), 1e-6)
        key = (round(lat / lat_step), round(lon / lon_step))
        weight = min(1.0, 30.0 / max(float(point["horizontal_accuracy_m"]), 1.0))
        bucket = buckets.setdefault(key, {"lat_sum": 0.0, "lon_sum": 0.0, "weight_sum": 0.0})
        bucket["lat_sum"] += lat * weight
        bucket["lon_sum"] += lon * weight
        bucket["weight_sum"] += weight
    if not buckets:
        return []
    max_weight = max(bucket["weight_sum"] for bucket in buckets.values()) or 1.0
    aggregated = []
    for bucket in buckets.values():
        aggregated.append(
            [
                round(bucket["lat_sum"] / bucket["weight_sum"], 6),
                round(bucket["lon_sum"] / bucket["weight_sum"], 6),
                round(min(1.0, bucket["weight_sum"] / max_weight), 4),
            ]
        )
    return aggregated


def _bucket_float(value: float, *, step: float) -> float:
    if step <= 0:
        return value
    return round(round(value / step) * step, 6)


def _bucket_bbox_for_zoom(
    bbox: tuple[float, float, float, float] | None,
    *,
    zoom: int,
) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    step = max((_heat_cell_m(zoom) / 111320.0) * 0.5, 1e-5)
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        round(math.floor(min_lon / step) * step, 6),
        round(math.floor(min_lat / step) * step, 6),
        round(math.ceil(max_lon / step) * step, 6),
        round(math.ceil(max_lat / step) * step, 6),
    )


def _detect_stops(
    points_asc: list[dict[str, Any]],
    *,
    stop_radius_m: int,
    stop_min_duration_min: int,
) -> list[dict[str, Any]]:
    minimum_ms = stop_min_duration_min * 60000
    index = 0
    stops = []
    while index < len(points_asc):
        anchor = points_asc[index]
        cursor = index + 1
        while cursor < len(points_asc) and _haversine_m(anchor, points_asc[cursor]) <= stop_radius_m:
            cursor += 1
        if cursor > index + 1:
            duration_ms = (_point_dt(points_asc[cursor - 1]) - _point_dt(anchor)).total_seconds() * 1000
            if duration_ms >= minimum_ms:
                midpoint = points_asc[(index + cursor - 1) // 2]
                stops.append(
                    {
                        "lat": float(midpoint["latitude"]),
                        "lon": float(midpoint["longitude"]),
                        "radius": stop_radius_m,
                        "durationMin": round(duration_ms / 60000),
                        "startTimeUtc": anchor["point_timestamp_utc"],
                        "endTimeUtc": points_asc[cursor - 1]["point_timestamp_utc"],
                        "startLabel": (anchor["point_timestamp_local"] or "")[11:16],
                        "endLabel": (points_asc[cursor - 1]["point_timestamp_local"] or "")[11:16],
                        "pointsCount": cursor - index,
                    }
                )
                index = cursor
                continue
        index += 1
    return stops


def _serialize_daytracks(points_asc: list[dict[str, Any]], *, zoom: int, route_time_gap_min: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for point in points_asc:
        grouped.setdefault(str(point["point_date_local"]), []).append(point)
    daytracks = []
    for index, (day, items) in enumerate(sorted(grouped.items())):
        segments = _segment_track(items, time_gap_ms=route_time_gap_min * 60000, dist_gap_m=200000)
        daytracks.append(
            {
                "day": day,
                "color": _palette_color(index),
                "labelPoint": [float(items[0]["latitude"]), float(items[0]["longitude"])],
                "segments": [_simplify_segment(segment, zoom) for segment in segments],
                "pointsCount": len(items),
            }
        )
    return daytracks


def _serialize_map_point(point: dict[str, Any], latest_point_id: int) -> dict[str, Any]:
    return {
        "id": int(point["id"]),
        "lat": float(point["latitude"]),
        "lon": float(point["longitude"]),
        "timestampLocal": point["point_timestamp_local"],
        "timestampUtc": point["point_timestamp_utc"],
        "accuracyM": float(point["horizontal_accuracy_m"]),
        "source": point["source"] or "",
        "isLatest": int(point["id"]) == int(latest_point_id),
    }


def _serialize_latest_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(point["id"]),
        "lat": float(point["latitude"]),
        "lon": float(point["longitude"]),
        "timestampLocal": point["point_timestamp_local"],
        "timestampUtc": point["point_timestamp_utc"],
        "accuracyM": float(point["horizontal_accuracy_m"]),
        "source": point["source"] or "",
    }


def _serialize_log_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(point["id"]),
        "lat": float(point["latitude"]),
        "lon": float(point["longitude"]),
        "timestampLocal": point["point_timestamp_local"],
        "accuracyM": float(point["horizontal_accuracy_m"]),
        "source": point["source"] or "",
        "captureMode": point["capture_mode"] or "",
        "requestId": point["request_id"] or "",
    }


def _adaptive_timeline_sample(points_asc: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    capped_limit = max(2, int(limit))
    if len(points_asc) <= capped_limit:
        return points_asc
    first_ts = _point_dt(points_asc[0]).timestamp()
    last_ts = _point_dt(points_asc[-1]).timestamp()
    if last_ts <= first_ts:
        step = max(1, len(points_asc) // capped_limit)
        sampled = points_asc[::step][: capped_limit - 1]
        if sampled[-1]["id"] != points_asc[-1]["id"]:
            sampled.append(points_asc[-1])
        return sampled
    bucket_count = max(2, capped_limit // 3)
    span = max((last_ts - first_ts) / bucket_count, 1.0)
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(bucket_count)]
    for point in points_asc:
        bucket_index = min(bucket_count - 1, int((_point_dt(point).timestamp() - first_ts) / span))
        buckets[bucket_index].append(point)
    sampled: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for bucket in buckets:
        if not bucket:
            continue
        picks = [bucket[0], bucket[-1]]
        if len(bucket) > 2:
            picks.insert(1, bucket[len(bucket) // 2])
        for point in picks:
            point_id = int(point["id"])
            if point_id in seen_ids:
                continue
            sampled.append(point)
            seen_ids.add(point_id)
    sampled.sort(key=_point_dt)
    if len(sampled) > capped_limit:
        step = max(1, len(sampled) // capped_limit)
        sampled = sampled[::step][: capped_limit - 1] + [sampled[-1]]
        sampled = sorted({int(point["id"]): point for point in sampled}.values(), key=_point_dt)
    return sampled


def _build_timeline_markers(
    points_asc: list[dict[str, Any]],
    *,
    stop_min_duration_min: int,
    stop_radius_m: int,
    precomputed_day_markers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not points_asc:
        return list(precomputed_day_markers or [])
    markers: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    if precomputed_day_markers:
        for marker in precomputed_day_markers:
            day = str(marker.get("label") or "")
            timestamp_utc = marker.get("timestampUtc")
            if not day or not timestamp_utc:
                continue
            key = ("day", day)
            if key in seen_keys:
                continue
            markers.append({"type": "day", "timestampUtc": timestamp_utc, "label": day})
            seen_keys.add(key)
    else:
        previous_day = None
        for point in points_asc:
            day = point.get("point_date_local") or (point.get("point_timestamp_local") or "")[:10]
            if day and day != previous_day:
                key = ("day", day)
                if key not in seen_keys:
                    markers.append({"type": "day", "timestampUtc": point["point_timestamp_utc"], "label": day})
                    seen_keys.add(key)
            previous_day = day
    for stop in _detect_stops(
        points_asc,
        stop_radius_m=stop_radius_m,
        stop_min_duration_min=stop_min_duration_min,
    ):
        timestamp_utc = stop["startTimeUtc"]
        key = ("stop", timestamp_utc)
        if key in seen_keys:
            continue
        markers.append(
            {
                "type": "stop",
                "timestampUtc": timestamp_utc,
                "label": f"Stop {stop['durationMin']} min",
                "durationMin": stop["durationMin"],
            }
        )
        seen_keys.add(key)
    markers.sort(key=lambda item: item["timestampUtc"])
    return markers
