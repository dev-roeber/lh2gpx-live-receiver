from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import require_admin_access

_SCHEMA_PATH = Path(__file__).parents[2] / "sql" / "geofencing_v1.sql"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


class CircleGeofenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geofence_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=1_000_000)
    hysteresis_m: float = Field(default=0, ge=0, le=1_000_000)
    enabled: bool = False

    @field_validator("geofence_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("geofence_id contains unsupported characters")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class CircleGeofenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: float | None = Field(default=None, gt=0, le=1_000_000)
    hysteresis_m: float | None = Field(default=None, ge=0, le=1_000_000)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


def _enabled(request: Request) -> None:
    if not request.app.state.settings.geofencing_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geofencing is disabled")


def _connection(request: Request) -> sqlite3.Connection:
    connection = sqlite3.connect(request.app.state.storage.sqlite_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(geofences)")}
        if "hysteresis_m" not in columns:
            connection.execute(
                "ALTER TABLE geofences ADD COLUMN hysteresis_m REAL NOT NULL DEFAULT 0.0 CHECK (hysteresis_m >= 0.0)"
            )
        connection.commit()
        return connection
    except Exception:
        connection.close()
        raise


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "geofenceId": row["geofence_id"],
        "name": row["name"],
        "geometryType": row["geometry_type"],
        "enabled": bool(row["enabled"]),
        "centerLatitude": row["center_latitude"],
        "centerLongitude": row["center_longitude"],
        "radiusM": row["radius_m"],
        "hysteresisM": row["hysteresis_m"],
        "createdAtUtc": row["created_at_utc"],
        "updatedAtUtc": row["updated_at_utc"],
    }


def register_geofence_routes(app: FastAPI) -> None:
    @app.get("/api/geofences", dependencies=[Depends(require_admin_access)])
    async def list_geofences(request: Request) -> dict[str, Any]:
        _enabled(request)
        connection = _connection(request)
        try:
            rows = connection.execute(
                "SELECT * FROM geofences WHERE geometry_type = 'circle' ORDER BY name COLLATE NOCASE, geofence_id"
            ).fetchall()
            return {"requestId": request.state.request_id, "geofences": [_serialize(row) for row in rows]}
        finally:
            connection.close()

    @app.post("/api/geofences", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_access)])
    async def create_geofence(request: Request, body: CircleGeofenceRequest = Body(...)) -> dict[str, Any]:
        _enabled(request)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        connection = _connection(request)
        try:
            try:
                connection.execute(
                    """INSERT INTO geofences
                       (geofence_id, name, geometry_type, enabled, center_latitude,
                        center_longitude, radius_m, hysteresis_m, created_at_utc, updated_at_utc)
                       VALUES (?, ?, 'circle', ?, ?, ?, ?, ?, ?, ?)""",
                    (body.geofence_id, body.name, int(body.enabled), body.center_latitude,
                     body.center_longitude, body.radius_m, body.hysteresis_m, now, now),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise HTTPException(status_code=409, detail="Geofence-ID bereits vorhanden oder ungültig") from exc
            row = connection.execute("SELECT * FROM geofences WHERE geofence_id = ?", (body.geofence_id,)).fetchone()
            return {"requestId": request.state.request_id, "geofence": _serialize(row)}
        finally:
            connection.close()

    @app.patch("/api/geofences/{geofence_id}", dependencies=[Depends(require_admin_access)])
    async def update_geofence(geofence_id: str, request: Request, body: CircleGeofenceUpdate = Body(...)) -> dict[str, Any]:
        _enabled(request)
        if not _ID_PATTERN.fullmatch(geofence_id):
            raise HTTPException(status_code=400, detail="Ungültige Geofence-ID")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="Keine Änderungen übergeben")
        column_map = {
            "name": "name", "center_latitude": "center_latitude", "center_longitude": "center_longitude",
            "radius_m": "radius_m", "hysteresis_m": "hysteresis_m", "enabled": "enabled",
        }
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        assignments = [f"{column_map[key]} = ?" for key in updates]
        values = list(updates.values()) + [now, geofence_id]
        connection = _connection(request)
        try:
            cursor = connection.execute(
                f"UPDATE geofences SET {', '.join(assignments)}, updated_at_utc = ? WHERE geofence_id = ? AND geometry_type = 'circle'",
                values,
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise HTTPException(status_code=404, detail="Geofence nicht gefunden")
            connection.commit()
            row = connection.execute("SELECT * FROM geofences WHERE geofence_id = ?", (geofence_id,)).fetchone()
            return {"requestId": request.state.request_id, "geofence": _serialize(row)}
        finally:
            connection.close()

    @app.get("/api/geofences/{geofence_id}/transitions", dependencies=[Depends(require_admin_access)])
    async def list_geofence_transitions(
        geofence_id: str,
        request: Request,
        limit: int = Query(default=20, ge=1, le=500),
    ) -> dict[str, Any]:
        _enabled(request)
        if not _ID_PATTERN.fullmatch(geofence_id):
            raise HTTPException(status_code=400, detail="Ungültige Geofence-ID")
        connection = _connection(request)
        try:
            exists = connection.execute(
                "SELECT 1 FROM geofences WHERE geofence_id = ?", (geofence_id,)
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="Geofence nicht gefunden")
            rows = connection.execute(
                """SELECT transition, point_timestamp_utc, latitude, longitude, detected_at_utc
                     FROM geofence_transitions
                    WHERE geofence_id = ?
                    ORDER BY transition_id DESC
                    LIMIT ?""",
                (geofence_id, limit),
            ).fetchall()
            return {
                "requestId": request.state.request_id,
                "geofenceId": geofence_id,
                "transitions": [
                    {
                        "transition": row["transition"],
                        "pointTimestampUtc": row["point_timestamp_utc"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "detectedAtUtc": row["detected_at_utc"],
                    }
                    for row in rows
                ],
            }
        finally:
            connection.close()

    @app.delete("/api/geofences/{geofence_id}", dependencies=[Depends(require_admin_access)])
    async def delete_geofence(geofence_id: str, request: Request) -> dict[str, Any]:
        _enabled(request)
        if not _ID_PATTERN.fullmatch(geofence_id):
            raise HTTPException(status_code=400, detail="Ungültige Geofence-ID")
        connection = _connection(request)
        try:
            cursor = connection.execute("DELETE FROM geofences WHERE geofence_id = ?", (geofence_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                raise HTTPException(status_code=404, detail="Geofence nicht gefunden")
            connection.commit()
            return {"requestId": request.state.request_id, "deleted": True, "geofenceId": geofence_id}
        finally:
            connection.close()
