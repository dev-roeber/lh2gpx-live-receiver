"""Opt-in circle-geofence evaluation.

This module is intentionally not imported by the ingestion path.  Callers must
construct :class:`GeofenceEngine` with ``enabled=True`` and pass each point
explicitly.  Historical points additionally require ``process_historical=True``
and ``historical=True`` on that call.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

_EARTH_RADIUS_M = 6_371_008.8
_MAX_RADIUS_M = 1_000_000.0


@dataclass(frozen=True, slots=True)
class CircleGeofence:
    geofence_id: str
    name: str
    center_latitude: float
    center_longitude: float
    radius_m: float
    hysteresis_m: float = 0.0
    enabled: bool = False

    def __post_init__(self) -> None:
        if not self.geofence_id.strip() or not self.name.strip():
            raise ValueError("geofence_id and name must not be blank")
        if not -90 <= self.center_latitude <= 90 or not -180 <= self.center_longitude <= 180:
            raise ValueError("circle center is outside WGS84 bounds")
        if not math.isfinite(self.radius_m) or not 0 < self.radius_m <= _MAX_RADIUS_M:
            raise ValueError("radius_m must be between 0 and 1,000,000")
        if not math.isfinite(self.hysteresis_m) or self.hysteresis_m < 0:
            raise ValueError("hysteresis_m must be non-negative")


@dataclass(frozen=True, slots=True)
class GeofencePoint:
    subject_key: str
    point_source: str
    point_key: str
    timestamp_utc: datetime
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not self.subject_key.strip() or not self.point_key.strip():
            raise ValueError("subject_key and point_key must not be blank")
        if self.point_source not in {"receiver", "dawarich"}:
            raise ValueError("point_source must be receiver or dawarich")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("point is outside WGS84 bounds")

    @property
    def normalized_timestamp(self) -> str:
        return self.timestamp_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class GeofenceEvent:
    geofence_id: str
    subject_key: str
    point_source: str
    point_key: str
    transition: str
    point_timestamp_utc: str
    latitude: float
    longitude: float


def distance_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Return the great-circle distance in metres using the WGS84 sphere mean."""
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    dlat = lat_b - lat_a
    dlon = math.radians((longitude_b - longitude_a + 180.0) % 360.0 - 180.0)
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * math.asin(math.sqrt(min(1.0, haversine)))


class GeofenceEngine:
    """Evaluate explicitly supplied new points against enabled circle zones."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        enabled: bool = False,
        process_historical: bool = False,
    ) -> None:
        self.connection = connection
        self.enabled = enabled
        self.process_historical = process_historical

    def evaluate_point(self, point: GeofencePoint, *, historical: bool = False) -> list[GeofenceEvent]:
        if not self.enabled or (historical and not self.process_historical):
            return []
        geofences = self._enabled_circles()
        return self.evaluate(point, geofences)

    def evaluate(self, point: GeofencePoint, geofences: Iterable[CircleGeofence]) -> list[GeofenceEvent]:
        if not self.enabled:
            return []
        events: list[GeofenceEvent] = []
        with self.connection:
            for geofence in geofences:
                if not geofence.enabled:
                    continue
                event = self._evaluate_one(point, geofence)
                if event is not None:
                    events.append(event)
        return events

    def _enabled_circles(self) -> list[CircleGeofence]:
        rows = self.connection.execute(
            """SELECT geofence_id, name, geometry_type, enabled,
                      center_latitude, center_longitude, radius_m, hysteresis_m
                 FROM geofences WHERE enabled = 1 AND geometry_type = 'circle'"""
        ).fetchall()
        return [
            CircleGeofence(
                geofence_id=row[0], name=row[1], center_latitude=row[4],
                center_longitude=row[5], radius_m=row[6], hysteresis_m=row[7], enabled=True,
            )
            for row in rows
        ]

    def _evaluate_one(self, point: GeofencePoint, geofence: CircleGeofence) -> GeofenceEvent | None:
        row = self.connection.execute(
            """SELECT is_inside, last_point_timestamp_utc
                 FROM geofence_subject_state
                 WHERE geofence_id = ? AND subject_key = ?""",
            (geofence.geofence_id, point.subject_key),
        ).fetchone()
        timestamp = point.normalized_timestamp
        if row is not None and timestamp < row[1]:
            return None

        distance = distance_m(point.latitude, point.longitude, geofence.center_latitude, geofence.center_longitude)
        previous_inside = None if row is None else bool(row[0])
        if previous_inside is None:
            is_inside = distance <= geofence.radius_m
            transition = "enter" if is_inside else None
        elif previous_inside:
            is_inside = distance <= geofence.radius_m + geofence.hysteresis_m
            transition = "exit" if not is_inside else None
        else:
            is_inside = distance <= geofence.radius_m
            transition = "enter" if is_inside else None

        event = None
        if transition is not None:
            cursor = self.connection.execute(
                """INSERT OR IGNORE INTO geofence_transitions
                   (geofence_id, subject_key, point_source, point_key, transition,
                    point_timestamp_utc, latitude, longitude, detected_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (geofence.geofence_id, point.subject_key, point.point_source, point.point_key,
                 transition, timestamp, point.latitude, point.longitude,
                 datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            )
            if cursor.rowcount == 1:
                event = GeofenceEvent(
                    geofence_id=geofence.geofence_id, subject_key=point.subject_key,
                    point_source=point.point_source, point_key=point.point_key,
                    transition=transition, point_timestamp_utc=timestamp,
                    latitude=point.latitude, longitude=point.longitude,
                )

        self.connection.execute(
            """INSERT INTO geofence_subject_state
               (geofence_id, subject_key, is_inside, last_point_source, last_point_key,
                last_point_timestamp_utc, last_latitude, last_longitude, updated_at_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(geofence_id, subject_key) DO UPDATE SET
                 is_inside = excluded.is_inside,
                 last_point_source = excluded.last_point_source,
                 last_point_key = excluded.last_point_key,
                 last_point_timestamp_utc = excluded.last_point_timestamp_utc,
                 last_latitude = excluded.last_latitude,
                 last_longitude = excluded.last_longitude,
                 updated_at_utc = excluded.updated_at_utc""",
            (geofence.geofence_id, point.subject_key, int(is_inside), point.point_source, point.point_key,
             timestamp, point.latitude, point.longitude, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        )
        return event
