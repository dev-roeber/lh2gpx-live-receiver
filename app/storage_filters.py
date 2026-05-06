from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage_geo import _slippy_tile_x, _slippy_tile_y, _tile_key


def _build_shared_filters(
    *,
    date_from: str | None,
    date_to: str | None,
    time_from: str | None,
    time_to: str | None,
    session_id: str | None,
    capture_mode: str | None,
    source: str | None,
    search: str | None,
    time_column: str,
    local_date_column: str | None,
    local_time_column: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    parameters: list[Any] = []

    if date_from:
        if local_date_column and "T" not in date_from:
            clauses.append(f"{local_date_column} >= ?")
            parameters.append(date_from)
        else:
            clauses.append(f"{time_column} >= ?")
            parameters.append(_normalize_datetime_filter(date_from, end_of_day=False))
    if date_to:
        if local_date_column and "T" not in date_to:
            clauses.append(f"{local_date_column} <= ?")
            parameters.append(date_to)
        else:
            clauses.append(f"{time_column} <= ?")
            parameters.append(_normalize_datetime_filter(date_to, end_of_day=True))
    if time_from and local_time_column:
        clauses.append(f"{local_time_column} >= ?")
        parameters.append(time_from)
    if time_to and local_time_column:
        clauses.append(f"{local_time_column} <= ?")
        parameters.append(time_to)
    if session_id:
        clauses.append("session_id = ?")
        parameters.append(session_id)
    if capture_mode:
        clauses.append("capture_mode = ?")
        parameters.append(capture_mode)
    if source:
        clauses.append("source = ?")
        parameters.append(source)
    if search:
        like_value = f"%{search.strip()}%"
        clauses.append("(session_id LIKE ? OR source LIKE ? OR capture_mode LIKE ? OR request_id LIKE ?)")
        parameters.extend([like_value, like_value, like_value, like_value])

    if not clauses:
        return "", parameters
    return f"WHERE {' AND '.join(clauses)}", parameters


def _append_bbox_filter(
    where_clause: str,
    parameters: list[Any],
    bbox: tuple[float, float, float, float] | None,
    *,
    spatial_zoom_hint: int | None = None,
) -> tuple[str, list[Any]]:
    if not bbox:
        return where_clause, parameters
    min_lon, min_lat, max_lon, max_lat = bbox
    clauses = [] if not where_clause else [where_clause.removeprefix("WHERE ").strip()]
    tile_key_clause, tile_key_parameters = _build_tile_key_bbox_clause(bbox, zoom_hint=spatial_zoom_hint)
    tile_clause, tile_parameters = _build_tile_bbox_clause(bbox, zoom_hint=spatial_zoom_hint) if tile_key_clause is None else (None, [])
    if min_lon <= max_lon:
        clauses.append(
            "id IN (SELECT id FROM gps_points_rtree WHERE min_lon <= ? AND max_lon >= ? AND min_lat <= ? AND max_lat >= ?)"
        )
        parameters = [*parameters, max_lon, min_lon, max_lat, min_lat]
    else:
        clauses.append(
            """id IN (
                SELECT id FROM gps_points_rtree
                WHERE min_lat <= ? AND max_lat >= ?
                  AND ((min_lon <= ? AND max_lon >= ?) OR (min_lon <= ? AND max_lon >= ?))
            )"""
        )
        parameters = [*parameters, max_lat, min_lat, 180.0, min_lon, max_lon, -180.0]
    if tile_key_clause:
        clauses.append(tile_key_clause)
        parameters = [*parameters, *tile_key_parameters]
    elif tile_clause:
        clauses.append(tile_clause)
        parameters = [*parameters, *tile_parameters]
    return f"WHERE {' AND '.join(clauses)}", parameters


def _build_tile_key_bbox_clause(
    bbox: tuple[float, float, float, float],
    *,
    zoom_hint: int | None,
) -> tuple[str | None, list[Any]]:
    if zoom_hint is None:
        return None, []
    min_lon, min_lat, max_lon, max_lat = bbox
    tile_zoom = 14 if zoom_hint >= 13 else 10
    scale = 1 << tile_zoom
    clamped_min_lat = max(-85.05112878, min(85.05112878, min_lat))
    clamped_max_lat = max(-85.05112878, min(85.05112878, max_lat))
    y_top = _slippy_tile_y(clamped_max_lat, zoom=tile_zoom)
    y_bottom = _slippy_tile_y(clamped_min_lat, zoom=tile_zoom)
    min_y = min(y_top, y_bottom)
    max_y = max(y_top, y_bottom)
    if min_lon <= max_lon:
        x_ranges = [(
            min(_slippy_tile_x(min_lon, zoom=tile_zoom), _slippy_tile_x(max_lon, zoom=tile_zoom)),
            max(_slippy_tile_x(min_lon, zoom=tile_zoom), _slippy_tile_x(max_lon, zoom=tile_zoom)),
        )]
    else:
        x_ranges = [
            (_slippy_tile_x(min_lon, zoom=tile_zoom), scale - 1),
            (0, _slippy_tile_x(max_lon, zoom=tile_zoom)),
        ]
    total_tiles = sum((max_x - min_x + 1) * (max_y - min_y + 1) for min_x, max_x in x_ranges)
    if total_tiles <= 0 or total_tiles > 256:
        return None, []
    keys: list[int] = []
    for min_x, max_x in x_ranges:
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                keys.append(_tile_key(x, y, zoom=tile_zoom))
    if not keys:
        return None, []
    key_column = f"tile_z{tile_zoom}_key"
    placeholders = ",".join("?" for _ in keys)
    return f"{key_column} IN ({placeholders})", keys


def _build_tile_bbox_clause(
    bbox: tuple[float, float, float, float],
    *,
    zoom_hint: int | None,
) -> tuple[str | None, list[Any]]:
    if zoom_hint is None:
        return None, []
    min_lon, min_lat, max_lon, max_lat = bbox
    tile_zoom = 14 if zoom_hint >= 13 else 10
    x_column = f"tile_z{tile_zoom}_x"
    y_column = f"tile_z{tile_zoom}_y"
    clamped_min_lat = max(-85.05112878, min(85.05112878, min_lat))
    clamped_max_lat = max(-85.05112878, min(85.05112878, max_lat))
    y_top = _slippy_tile_y(clamped_max_lat, zoom=tile_zoom)
    y_bottom = _slippy_tile_y(clamped_min_lat, zoom=tile_zoom)
    min_y = min(y_top, y_bottom)
    max_y = max(y_top, y_bottom)
    if min_lon <= max_lon:
        min_x = min(_slippy_tile_x(min_lon, zoom=tile_zoom), _slippy_tile_x(max_lon, zoom=tile_zoom))
        max_x = max(_slippy_tile_x(min_lon, zoom=tile_zoom), _slippy_tile_x(max_lon, zoom=tile_zoom))
        return f"{x_column} BETWEEN ? AND ? AND {y_column} BETWEEN ? AND ?", [min_x, max_x, min_y, max_y]
    return (
        f"(({x_column} BETWEEN ? AND ? AND {y_column} BETWEEN ? AND ?) OR ({x_column} BETWEEN ? AND ? AND {y_column} BETWEEN ? AND ?))",
        [
            _slippy_tile_x(min_lon, zoom=tile_zoom),
            (1 << tile_zoom) - 1,
            min_y,
            max_y,
            0,
            _slippy_tile_x(max_lon, zoom=tile_zoom),
            min_y,
            max_y,
        ],
    )


def _normalize_datetime_filter(value: str, *, end_of_day: bool) -> str:
    if "T" in value:
        return value
    suffix = "T23:59:59.999999+00:00" if end_of_day else "T00:00:00+00:00"
    return f"{value}{suffix}"


def _duration_seconds(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        return None
    return max(0, int((end_dt - start_dt).total_seconds()))


def _file_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    if not exists:
        return {"path": str(path), "exists": False, "sizeBytes": 0, "lastModifiedUtc": None}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "sizeBytes": stat.st_size,
        "lastModifiedUtc": isoformat_utc(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
    }


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()
