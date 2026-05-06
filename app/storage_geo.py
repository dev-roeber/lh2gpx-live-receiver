from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def _storage_point_dt(point: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(point["point_timestamp_utc"]))


def _storage_haversine_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1 = math.radians(float(a["latitude"]))
    lat2 = math.radians(float(b["latitude"]))
    d_lat = lat2 - lat1
    d_lon = math.radians(float(b["longitude"]) - float(a["longitude"]))
    hav = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(hav)))


def _storage_segment_track(
    points_asc: list[dict[str, Any]],
    *,
    time_gap_ms: int,
    dist_gap_m: int,
) -> list[list[dict[str, Any]]]:
    if not points_asc:
        return []
    segments = [[points_asc[0]]]
    previous = points_asc[0]
    for point in points_asc[1:]:
        delta_ms = (_storage_point_dt(point) - _storage_point_dt(previous)).total_seconds() * 1000
        if delta_ms > time_gap_ms or _storage_haversine_m(previous, point) > dist_gap_m:
            segments.append([])
        segments[-1].append(point)
        previous = point
    return [segment for segment in segments if len(segment) >= 2]


def _storage_detect_stops(
    points_asc: list[dict[str, Any]],
    *,
    stop_radius_m: int,
    stop_min_duration_min: int,
) -> list[dict[str, Any]]:
    minimum_ms = stop_min_duration_min * 60000
    index = 0
    stops: list[dict[str, Any]] = []
    while index < len(points_asc):
        anchor = points_asc[index]
        cursor = index + 1
        while cursor < len(points_asc) and _storage_haversine_m(anchor, points_asc[cursor]) <= stop_radius_m:
            cursor += 1
        if cursor > index + 1:
            duration_ms = (_storage_point_dt(points_asc[cursor - 1]) - _storage_point_dt(anchor)).total_seconds() * 1000
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


def _storage_build_daytrack_rollups(
    points_asc: list[dict[str, Any]],
    *,
    route_time_gap_min: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for point in points_asc:
        grouped.setdefault(str(point["point_date_local"]), []).append(point)
    rollups: list[dict[str, Any]] = []
    for index, (day, items) in enumerate(sorted(grouped.items())):
        segments = _storage_segment_track(items, time_gap_ms=route_time_gap_min * 60000, dist_gap_m=200000)
        rollups.append(
            {
                "day": day,
                "colorIndex": index,
                "labelLat": float(items[0]["latitude"]),
                "labelLon": float(items[0]["longitude"]),
                "rawSegments": [
                    [[float(point["latitude"]), float(point["longitude"])] for point in segment]
                    for segment in segments
                ],
                "pointsCount": len(items),
            }
        )
    return rollups


def _storage_simplify_coords(segment: list[list[float]], zoom: int) -> list[list[float]]:
    if len(segment) <= 2:
        return segment
    target = max(2, min(len(segment), int(zoom * 1.5)))
    step = max(1, len(segment) // target)
    simplified = segment[::step]
    if simplified[-1] != segment[-1]:
        simplified.append(segment[-1])
    return simplified


def _storage_palette_color(index: int) -> str:
    palette = ["#0A84FF", "#30D158", "#FF9F0A", "#BF5AF2", "#FF375F", "#64D2FF", "#FFD60A"]
    return palette[index % len(palette)]


def _compute_bounding_box(points: list[dict[str, Any]]) -> dict[str, float] | None:
    if not points:
        return None
    latitudes = [point["latitude"] for point in points]
    longitudes = [point["longitude"] for point in points]
    return {
        "minLatitude": min(latitudes),
        "maxLatitude": max(latitudes),
        "minLongitude": min(longitudes),
        "maxLongitude": max(longitudes),
    }


def _slippy_tile_x(longitude: float, *, zoom: int) -> int:
    scale = 1 << zoom
    normalized = ((float(longitude) + 180.0) / 360.0) * scale
    return max(0, min(scale - 1, int(normalized)))


def _slippy_tile_y(latitude: float, *, zoom: int) -> int:
    scale = 1 << zoom
    clamped_lat = max(-85.05112878, min(85.05112878, float(latitude)))
    lat_rad = math.radians(clamped_lat)
    mercator = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0
    return max(0, min(scale - 1, int(mercator * scale)))


def _tile_key(x: int, y: int, *, zoom: int) -> int:
    value = 0
    for bit in range(zoom):
        value |= ((x >> bit) & 1) << (2 * bit)
        value |= ((y >> bit) & 1) << (2 * bit + 1)
    return value


def _tile_columns_for_row(latitude: float, longitude: float, row_id: int) -> tuple[int, int, int, int, int, int, int]:
    z10_x = _slippy_tile_x(longitude, zoom=10)
    z10_y = _slippy_tile_y(latitude, zoom=10)
    z14_x = _slippy_tile_x(longitude, zoom=14)
    z14_y = _slippy_tile_y(latitude, zoom=14)
    return (
        z10_x,
        z10_y,
        z14_x,
        z14_y,
        _tile_key(z10_x, z10_y, zoom=10),
        _tile_key(z14_x, z14_y, zoom=14),
        row_id,
    )
