from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from .config import Settings
from .models import LiveLocationRequest, PointFilters, RequestFilters, RequestMetadata, payload_to_json
from .storage_filters import (
    _append_bbox_filter,
    _build_shared_filters,
    _duration_seconds,
    _file_info,
    isoformat_utc,
)
from .storage_geo import (
    _compute_bounding_box,
    _slippy_tile_x,
    _slippy_tile_y,
    _storage_build_daytrack_rollups,
    _storage_detect_stops,
    _storage_palette_color,
    _storage_segment_track,
    _storage_simplify_coords,
    _tile_columns_for_row,
    _tile_key,
)

_DEFAULT_ROUTE_TIME_GAP_MIN = 15
_DEFAULT_STOP_MIN_DURATION_MIN = 5
_DEFAULT_STOP_RADIUS_M = 100


class StorageError(RuntimeError):
    public_message = "Storage unavailable."
    error_category = "storage_unavailable"


class StorageNotReadyError(StorageError):
    public_message = "Storage is not ready."
    error_category = "storage_not_ready"


class StorageWriteError(StorageError):
    public_message = "Storage write failed."
    error_category = "storage_write_failed"


@dataclass(slots=True)
class ReadinessState:
    is_ready: bool
    writable: bool
    message: str
    sqlite_path: str
    raw_ndjson_path: str


class ReceiverStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sqlite_path = settings.sqlite_path
        self.raw_ndjson_path = settings.raw_payload_ndjson_path
        self._lock = Lock()
        self._ready = False
        self._last_error: str | None = None
        self._timezone = ZoneInfo(settings.local_timezone)

    def startup(self) -> None:
        try:
            self._prepare_filesystem()
            with self._connect() as connection:
                self._apply_migrations(connection)
                self._maybe_import_legacy_ndjson(connection)
            self._ready = True
            self._last_error = None
        except Exception as exc:
            self._ready = False
            self._last_error = str(exc)

    def readiness(self) -> ReadinessState:
        writable = self._is_writable()
        if self._ready and writable:
            return ReadinessState(
                is_ready=True,
                writable=True,
                message="storage ready",
                sqlite_path=str(self.sqlite_path),
                raw_ndjson_path=str(self.raw_ndjson_path),
            )

        message = self._last_error or "storage not initialized"
        return ReadinessState(
            is_ready=False,
            writable=writable,
            message=message,
            sqlite_path=str(self.sqlite_path),
            raw_ndjson_path=str(self.raw_ndjson_path),
        )

    def ingest_success(
        self,
        payload: LiveLocationRequest,
        metadata: RequestMetadata,
        raw_payload_text: str,
    ) -> dict[str, Any]:
        self._require_ready()
        payload_json = payload_to_json(payload)
        received_at = metadata.received_at_utc.astimezone(timezone.utc)
        points = payload.points
        first_ts = min(point.timestamp for point in points).astimezone(timezone.utc)
        last_ts = max(point.timestamp for point in points).astimezone(timezone.utc)
        raw_payload_reference = self._append_raw_payload(
            request_id=metadata.request_id,
            received_at_utc=received_at,
            payload_json=payload_json,
        )

        with self._locked_transaction() as connection:
            connection.execute(
                """
                INSERT INTO ingest_requests (
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    source,
                    session_id,
                    capture_mode,
                    points_count,
                    first_point_ts_utc,
                    last_point_ts_utc,
                    user_agent,
                    remote_addr,
                    proxied_ip,
                    ingest_status,
                    http_status,
                    error_category,
                    error_detail,
                    raw_payload_json,
                    raw_payload_reference
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.request_id,
                    isoformat_utc(received_at),
                    isoformat_utc(payload.sentAt),
                    payload.source,
                    str(payload.sessionID),
                    payload.captureMode,
                    len(points),
                    isoformat_utc(first_ts),
                    isoformat_utc(last_ts),
                    metadata.user_agent,
                    metadata.remote_addr,
                    metadata.proxied_ip,
                    "accepted",
                    202,
                    None,
                    None,
                    raw_payload_text,
                    raw_payload_reference,
                ),
            )

            point_rows = []
            for point in points:
                point_timestamp_utc = point.timestamp.astimezone(timezone.utc)
                point_timestamp_local = point.timestamp.astimezone(self._timezone)
                point_rows.append(
                    (
                        metadata.request_id,
                        isoformat_utc(received_at),
                        isoformat_utc(payload.sentAt),
                        isoformat_utc(point_timestamp_utc),
                        point.latitude,
                        point.longitude,
                        point.horizontalAccuracyM,
                        payload.source,
                        str(payload.sessionID),
                        payload.captureMode,
                point_timestamp_local.strftime("%Y-%m-%d"),
                point_timestamp_local.strftime("%H:%M:%S"),
                point_timestamp_local.isoformat(),
                _slippy_tile_x(point.longitude, zoom=10),
                _slippy_tile_y(point.latitude, zoom=10),
                _slippy_tile_x(point.longitude, zoom=14),
                _slippy_tile_y(point.latitude, zoom=14),
                _tile_key(_slippy_tile_x(point.longitude, zoom=10), _slippy_tile_y(point.latitude, zoom=10), zoom=10),
                _tile_key(_slippy_tile_x(point.longitude, zoom=14), _slippy_tile_y(point.latitude, zoom=14), zoom=14),
                    )
                )

            connection.executemany(
                """
                INSERT INTO gps_points (
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    source,
                    session_id,
                    capture_mode,
                    point_date_local,
                    point_time_local,
                    point_timestamp_local,
                    tile_z10_x,
                    tile_z10_y,
                    tile_z14_x,
                    tile_z14_y,
                    tile_z10_key,
                    tile_z14_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                point_rows,
            )
            self._update_point_rollups(connection, point_rows)
            self._update_timeline_day_markers(connection, point_rows)
            self._update_session_track_rollups(connection, point_rows)

        return {
            "requestId": metadata.request_id,
            "pointsAccepted": len(points),
            "storage": {
                "sqlitePath": str(self.sqlite_path),
                "rawPayloadNdjsonPath": str(self.raw_ndjson_path),
                "rawPayloadNdjsonEnabled": self.settings.raw_payload_ndjson_enabled,
            },
            "firstPointTimestampUtc": isoformat_utc(first_ts),
            "lastPointTimestampUtc": isoformat_utc(last_ts),
        }

    def record_failure(
        self,
        *,
        metadata: RequestMetadata,
        ingest_status: str,
        http_status: int,
        error_category: str,
        error_detail: str,
        raw_payload_text: str,
        source: str | None = None,
        session_id: str | None = None,
        capture_mode: str | None = None,
        sent_at_utc: str | None = None,
        points_count: int = 0,
        first_point_ts_utc: str | None = None,
        last_point_ts_utc: str | None = None,
    ) -> None:
        if not self._ready:
            return

        try:
            with self._locked_transaction() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO ingest_requests (
                        request_id,
                        received_at_utc,
                        sent_at_utc,
                        source,
                        session_id,
                        capture_mode,
                        points_count,
                        first_point_ts_utc,
                        last_point_ts_utc,
                        user_agent,
                        remote_addr,
                        proxied_ip,
                        ingest_status,
                        http_status,
                        error_category,
                        error_detail,
                        raw_payload_json,
                        raw_payload_reference
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.request_id,
                        isoformat_utc(metadata.received_at_utc),
                        sent_at_utc,
                        source,
                        session_id,
                        capture_mode,
                        points_count,
                        first_point_ts_utc,
                        last_point_ts_utc,
                        metadata.user_agent,
                        metadata.remote_addr,
                        metadata.proxied_ip,
                        ingest_status,
                        http_status,
                        error_category,
                        error_detail[:1000],
                        raw_payload_text[:50000],
                        None,
                    ),
                )
        except Exception:
            # Failure logging must never hide the original HTTP error.
            return

    def get_stats(self) -> dict[str, Any]:
        self._require_ready()
        since_24h = isoformat_utc(datetime.now(timezone.utc) - timedelta(hours=24))
        since_7d = isoformat_utc(datetime.now(timezone.utc) - timedelta(days=7))
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    SUM(CASE WHEN ingest_status = 'accepted' THEN 1 ELSE 0 END) AS accepted_requests,
                    SUM(CASE WHEN ingest_status != 'accepted' THEN 1 ELSE 0 END) AS failed_requests,
                    MAX(CASE WHEN ingest_status = 'accepted' THEN received_at_utc END) AS last_success_at,
                    MAX(CASE WHEN ingest_status != 'accepted' THEN received_at_utc END) AS last_failure_at,
                    COUNT(DISTINCT CASE WHEN ingest_status = 'accepted' THEN session_id END) AS total_sessions
                FROM ingest_requests
                """
            ).fetchone()

            # Echte Punkt-Anzahl direkt aus gps_points (kein denormalisierter Cache)
            gps_counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_points,
                    SUM(CASE WHEN point_timestamp_utc >= ? THEN 1 ELSE 0 END) AS points_24h,
                    SUM(CASE WHEN point_timestamp_utc >= ? THEN 1 ELSE 0 END) AS points_7d
                FROM gps_points
                """,
                (since_24h, since_7d),
            ).fetchone()

            period_rows = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_24h,
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_7d
                FROM ingest_requests
                WHERE ingest_status = 'accepted'
                """,
                (since_24h, since_7d),
            ).fetchone()

            points_per_day = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT point_date_local AS local_date, COUNT(*) AS points
                    FROM gps_points
                    GROUP BY point_date_local
                    ORDER BY point_date_local DESC
                    LIMIT 14
                    """
                ).fetchall()
            ]

            points_per_session = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT session_id, COUNT(*) AS points
                    FROM gps_points
                    GROUP BY session_id
                    ORDER BY points DESC, session_id ASC
                    LIMIT 20
                    """
                ).fetchall()
            ]

        readiness = self.readiness()
        return {
            "storage": {
                "sqlitePath": str(self.sqlite_path),
                "rawPayloadNdjsonPath": str(self.raw_ndjson_path),
                "legacyRequestNdjsonPath": str(self.settings.legacy_request_ndjson_path),
                "rawPayloadNdjsonEnabled": self.settings.raw_payload_ndjson_enabled,
                "isReady": readiness.is_ready,
                "writable": readiness.writable,
                "message": readiness.message,
            },
            "totals": {
                **dict(totals),
                "total_points": int(gps_counts["total_points"] or 0),
            },
            "periods": {
                **dict(period_rows),
                "points_24h": int(gps_counts["points_24h"] or 0),
                "points_7d": int(gps_counts["points_7d"] or 0),
            },
            "pointsPerDay": points_per_day,
            "pointsPerSession": points_per_session,
        }

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        self._require_ready()
        now_utc = datetime.now(timezone.utc)
        since_24h = isoformat_utc(now_utc - timedelta(hours=24))
        since_7d = isoformat_utc(now_utc - timedelta(days=7))
        today_local = now_utc.astimezone(self._timezone).strftime("%Y-%m-%d")

        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    SUM(CASE WHEN ingest_status = 'accepted' THEN 1 ELSE 0 END) AS accepted_requests,
                    SUM(CASE WHEN ingest_status != 'accepted' THEN 1 ELSE 0 END) AS failed_requests,
                    COUNT(DISTINCT CASE WHEN ingest_status = 'accepted' THEN session_id END) AS total_sessions,
                    MAX(CASE WHEN ingest_status = 'accepted' THEN received_at_utc END) AS last_success_at,
                    MAX(CASE WHEN ingest_status != 'accepted' THEN received_at_utc END) AS last_failure_at
                FROM ingest_requests
                """
            ).fetchone()

            # Echte Punkt-Anzahl direkt aus gps_points (nicht aus denormalisiertem points_count)
            gps_counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_points,
                    SUM(CASE WHEN point_timestamp_utc >= ? THEN 1 ELSE 0 END) AS points_24h,
                    SUM(CASE WHEN point_timestamp_utc >= ? THEN 1 ELSE 0 END) AS points_7d
                FROM gps_points
                """,
                (since_24h, since_7d),
            ).fetchone()

            periods = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_24h,
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_7d,
                    SUM(CASE WHEN ingest_status = 'accepted' AND substr(received_at_utc, 1, 10) = ? THEN 1 ELSE 0 END) AS requests_today,
                    SUM(CASE WHEN ingest_status = 'accepted' AND session_id IS NOT NULL AND received_at_utc >= ? THEN 1 ELSE 0 END) AS session_events_24h,
                    SUM(CASE WHEN ingest_status = 'accepted' AND session_id IS NOT NULL AND received_at_utc >= ? THEN 1 ELSE 0 END) AS session_events_7d
                FROM ingest_requests
                """,
                (since_24h, since_7d, today_local, since_24h, since_7d),
            ).fetchone()

            points_today = connection.execute(
                """
                SELECT COUNT(*) AS points_today
                FROM gps_points
                WHERE point_date_local = ?
                """,
                (today_local,),
            ).fetchone()

            session_counts = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT CASE WHEN ingest_status = 'accepted' AND received_at_utc >= ? THEN session_id END) AS sessions_24h,
                    COUNT(DISTINCT CASE WHEN ingest_status = 'accepted' AND received_at_utc >= ? THEN session_id END) AS sessions_7d
                FROM ingest_requests
                """,
                (since_24h, since_7d),
            ).fetchone()

            last_request = connection.execute(
                """
                SELECT
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    source,
                    session_id,
                    capture_mode,
                    points_count,
                    ingest_status,
                    http_status,
                    error_category,
                    error_detail
                FROM ingest_requests
                ORDER BY received_at_utc DESC, request_id DESC
                LIMIT 1
                """
            ).fetchone()

            last_success = connection.execute(
                """
                SELECT
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    source,
                    session_id,
                    capture_mode,
                    points_count,
                    ingest_status,
                    http_status
                FROM ingest_requests
                WHERE ingest_status = 'accepted'
                ORDER BY received_at_utc DESC, request_id DESC
                LIMIT 1
                """
            ).fetchone()

            last_failure = connection.execute(
                """
                SELECT
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    source,
                    session_id,
                    capture_mode,
                    points_count,
                    ingest_status,
                    http_status,
                    error_category,
                    error_detail
                FROM ingest_requests
                WHERE ingest_status != 'accepted'
                ORDER BY received_at_utc DESC, request_id DESC
                LIMIT 1
                """
            ).fetchone()

            latest_point = connection.execute(
                """
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode
                FROM gps_points
                ORDER BY point_timestamp_utc DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

            first_point = connection.execute(
                """
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode
                FROM gps_points
                ORDER BY point_timestamp_utc ASC, id ASC
                LIMIT 1
                """
            ).fetchone()

            accuracy = connection.execute(
                """
                SELECT
                    MIN(horizontal_accuracy_m) AS min_accuracy_m,
                    AVG(horizontal_accuracy_m) AS avg_accuracy_m,
                    MAX(horizontal_accuracy_m) AS max_accuracy_m
                FROM gps_points
                """
            ).fetchone()

            recent_requests = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        request_id,
                        received_at_utc,
                        sent_at_utc,
                        source,
                        session_id,
                        capture_mode,
                        points_count,
                        first_point_ts_utc,
                        last_point_ts_utc,
                        ingest_status,
                        http_status,
                        error_category,
                        error_detail
                    FROM ingest_requests
                    ORDER BY received_at_utc DESC, request_id DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]

            recent_points = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        id,
                        request_id,
                        received_at_utc,
                        sent_at_utc,
                        point_timestamp_utc,
                        point_timestamp_local,
                        point_date_local,
                        point_time_local,
                        latitude,
                        longitude,
                        horizontal_accuracy_m,
                        session_id,
                        source,
                        capture_mode
                    FROM gps_points
                    ORDER BY point_timestamp_utc DESC, id DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]

            recent_sessions = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        session_id,
                        MIN(source) AS source,
                        CASE
                            WHEN COUNT(DISTINCT capture_mode) = 1 THEN MIN(capture_mode)
                            ELSE 'mixed'
                        END AS capture_mode,
                        COUNT(*) AS points_count,
                        COUNT(DISTINCT request_id) AS requests_count,
                        AVG(horizontal_accuracy_m) AS avg_accuracy_m,
                        MIN(point_timestamp_utc) AS first_point_ts_utc,
                        MAX(point_timestamp_utc) AS last_point_ts_utc
                    FROM gps_points
                    GROUP BY session_id
                    ORDER BY last_point_ts_utc DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]

            top_sessions = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        session_id,
                        MIN(source) AS source,
                        CASE
                            WHEN COUNT(DISTINCT capture_mode) = 1 THEN MIN(capture_mode)
                            ELSE 'mixed'
                        END AS capture_mode,
                        COUNT(*) AS points_count,
                        COUNT(DISTINCT request_id) AS requests_count,
                        AVG(horizontal_accuracy_m) AS avg_accuracy_m,
                        MIN(point_timestamp_utc) AS first_point_ts_utc,
                        MAX(point_timestamp_utc) AS last_point_ts_utc
                    FROM gps_points
                    GROUP BY session_id
                    ORDER BY points_count DESC, last_point_ts_utc DESC
                    LIMIT 5
                    """
                ).fetchall()
            ]

            points_per_day = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT point_date_local AS period_label, COUNT(*) AS value
                    FROM gps_points
                    GROUP BY point_date_local
                    ORDER BY point_date_local DESC
                    LIMIT 14
                    """
                ).fetchall()
            ]

            requests_per_day = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT substr(received_at_utc, 1, 10) AS period_label, COUNT(*) AS value
                    FROM ingest_requests
                    GROUP BY substr(received_at_utc, 1, 10)
                    ORDER BY period_label DESC
                    LIMIT 14
                    """
                ).fetchall()
            ]

            response_codes = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT http_status AS label, COUNT(*) AS value
                    FROM ingest_requests
                    GROUP BY http_status
                    ORDER BY value DESC, http_status ASC
                    """
                ).fetchall()
            ]

            source_distribution = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT source AS label, COUNT(*) AS value
                    FROM gps_points
                    GROUP BY source
                    ORDER BY value DESC, source ASC
                    """
                ).fetchall()
            ]

            capture_mode_distribution = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT capture_mode AS label, COUNT(*) AS value
                    FROM gps_points
                    GROUP BY capture_mode
                    ORDER BY value DESC, capture_mode ASC
                    """
                ).fetchall()
            ]

            error_distribution = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT COALESCE(error_category, 'none') AS label, COUNT(*) AS value
                    FROM ingest_requests
                    WHERE ingest_status != 'accepted'
                    GROUP BY COALESCE(error_category, 'none')
                    ORDER BY value DESC, label ASC
                    """
                ).fetchall()
            ]

        total_requests = int(totals["total_requests"] or 0)
        failed_requests = int(totals["failed_requests"] or 0)
        accepted_requests = int(totals["accepted_requests"] or 0)
        success_rate = round((accepted_requests / total_requests) * 100, 1) if total_requests else 0.0
        failure_rate = round((failed_requests / total_requests) * 100, 1) if total_requests else 0.0
        last_issue = dict(last_failure) if last_failure else None
        last_request_dict = dict(last_request) if last_request else None

        return {
            "generatedAtUtc": isoformat_utc(now_utc),
            "storage": {
                "sqlitePath": str(self.sqlite_path),
                "rawPayloadNdjsonPath": str(self.raw_ndjson_path),
                "legacyRequestNdjsonPath": str(self.settings.legacy_request_ndjson_path),
                "rawPayloadNdjsonEnabled": self.settings.raw_payload_ndjson_enabled,
                "readiness": asdict(self.readiness()),
                "sqliteFile": _file_info(self.sqlite_path),
                "sqliteWalFile": _file_info(self.sqlite_path.with_suffix(self.sqlite_path.suffix + "-wal")),
                "sqliteShmFile": _file_info(self.sqlite_path.with_suffix(self.sqlite_path.suffix + "-shm")),
                "rawPayloadFile": _file_info(self.raw_ndjson_path),
            },
            "totals": {
                "totalRequests": total_requests,
                "acceptedRequests": accepted_requests,
                "failedRequests": failed_requests,
                "totalPoints": int(gps_counts["total_points"] or 0),
                "totalSessions": int(totals["total_sessions"] or 0),
                "lastSuccessAt": totals["last_success_at"],
                "lastFailureAt": totals["last_failure_at"],
                "successRate": success_rate,
                "failureRate": failure_rate,
            },
            "periods": {
                "requests24h": int(periods["requests_24h"] or 0),
                "requests7d": int(periods["requests_7d"] or 0),
                "requestsToday": int(periods["requests_today"] or 0),
                "points24h": int(gps_counts["points_24h"] or 0),
                "points7d": int(gps_counts["points_7d"] or 0),
                "pointsToday": int(points_today["points_today"] or 0),
                "sessions24h": int(session_counts["sessions_24h"] or 0),
                "sessions7d": int(session_counts["sessions_7d"] or 0),
                "sessionEvents24h": int(periods["session_events_24h"] or 0),
                "sessionEvents7d": int(periods["session_events_7d"] or 0),
            },
            "latest": {
                "request": last_request_dict,
                "success": dict(last_success) if last_success else None,
                "failure": last_issue,
                "firstPoint": dict(first_point) if first_point else None,
                "lastPoint": dict(latest_point) if latest_point else None,
            },
            "accuracy": {
                "minAccuracyM": round(float(accuracy["min_accuracy_m"]), 2) if accuracy["min_accuracy_m"] is not None else None,
                "avgAccuracyM": round(float(accuracy["avg_accuracy_m"]), 2) if accuracy["avg_accuracy_m"] is not None else None,
                "maxAccuracyM": round(float(accuracy["max_accuracy_m"]), 2) if accuracy["max_accuracy_m"] is not None else None,
            },
            "lists": {
                "recentRequests": recent_requests,
                "recentPoints": recent_points,
                "recentSessions": recent_sessions,
                "topSessions": top_sessions,
                "pointsPerDay": points_per_day,
                "requestsPerDay": requests_per_day,
                "responseCodes": response_codes,
                "sourceDistribution": source_distribution,
                "captureModeDistribution": capture_mode_distribution,
                "errorDistribution": error_distribution,
            },
            "status": {
                "hasIssues": (not self.readiness().is_ready) or bool(last_issue) or bool(last_request_dict and last_request_dict["ingest_status"] != "accepted"),
                "lastErrorCategory": last_issue["error_category"] if last_issue else None,
                "lastErrorDetail": last_issue["error_detail"] if last_issue else None,
                "lastWarning": self._last_error or (last_issue["error_detail"] if last_issue else None),
                "lastHttpStatus": last_request_dict["http_status"] if last_request_dict else None,
                "lastIngestStatus": last_request_dict["ingest_status"] if last_request_dict else None,
            },
            "exports": [
                {"label": "CSV export", "format": "csv", "path": "/api/points?format=csv"},
                {"label": "JSON export", "format": "json", "path": "/api/points?format=json"},
                {"label": "NDJSON export", "format": "ndjson", "path": "/api/points?format=ndjson"},
            ],
        }

    def import_points(
        self,
        points: list[dict[str, Any]],
        *,
        source: str,
        session_id: str,
        request_id: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Bulk-insert GPS points from an import operation."""
        self._require_ready()
        now_utc = datetime.now(timezone.utc)
        received_iso = isoformat_utc(now_utc)

        point_rows = []
        invalid_rows = 0
        for p in points:
            try:
                ts_utc = p["timestamp_utc"]
                if isinstance(ts_utc, str):
                    ts_utc = datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
                ts_local = ts_utc.astimezone(self._timezone)
                point_rows.append((
                    request_id, received_iso, received_iso,
                    isoformat_utc(ts_utc),
                    float(p["latitude"]), float(p["longitude"]),
                    float(p.get("accuracy_m") or 0),
                    source, session_id,
                    p.get("capture_mode") or "imported",
                    ts_local.strftime("%Y-%m-%d"),
                    ts_local.strftime("%H:%M:%S"),
                    ts_local.isoformat(),
                    _slippy_tile_x(float(p["longitude"]), zoom=10),
                    _slippy_tile_y(float(p["latitude"]), zoom=10),
                    _slippy_tile_x(float(p["longitude"]), zoom=14),
                    _slippy_tile_y(float(p["latitude"]), zoom=14),
                    _tile_key(_slippy_tile_x(float(p["longitude"]), zoom=10), _slippy_tile_y(float(p["latitude"]), zoom=10), zoom=10),
                    _tile_key(_slippy_tile_x(float(p["longitude"]), zoom=14), _slippy_tile_y(float(p["latitude"]), zoom=14), zoom=14),
                ))
            except Exception:
                invalid_rows += 1

        valid_rows_before_dedupe = list(point_rows)
        all_valid_timestamps = [row[3] for row in valid_rows_before_dedupe]

        # 1) Duplikate innerhalb der Importdatei entfernen (gleicher Timestamp+Coords)
        seen_keys: set[tuple] = set()
        deduped: list = []
        for r in point_rows:
            key = (r[3], r[4], r[5])  # point_timestamp_utc, latitude, longitude
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(r)
        deduped_in_file = len(point_rows) - len(deduped)
        point_rows = deduped

        # 2) Bereits in der DB vorhandene Punkte herausfiltern (in Batches wegen SQLite-Variablenlimit)
        already_existing = 0
        if point_rows:
            _BATCH = 500
            ts_values = list({r[3] for r in point_rows})
            existing: set[tuple] = set()
            with self._connect() as check_conn:
                for i in range(0, len(ts_values), _BATCH):
                    batch = ts_values[i : i + _BATCH]
                    placeholders = ",".join("?" * len(batch))
                    rows = check_conn.execute(
                        f"SELECT point_timestamp_utc, latitude, longitude FROM gps_points "
                        f"WHERE point_timestamp_utc IN ({placeholders})",
                        batch,
                    ).fetchall()
                    existing.update((r[0], r[1], r[2]) for r in rows)
            before = len(point_rows)
            point_rows = [r for r in point_rows if (r[3], r[4], r[5]) not in existing]
            already_existing = before - len(point_rows)

        inserted = len(point_rows)
        skipped_total = invalid_rows + deduped_in_file + already_existing
        first_ts = min(all_valid_timestamps) if all_valid_timestamps else None
        last_ts = max(all_valid_timestamps) if all_valid_timestamps else None
        if progress_callback:
            progress_callback(
                {
                    "raw_points": len(points),
                    "processed_points": skipped_total,
                    "remaining_points": inserted,
                    "inserted_points": 0,
                    "skipped_total": skipped_total,
                }
            )
        if point_rows:
            ts_list = [r[3] for r in point_rows]
            inserted_first_ts, inserted_last_ts = min(ts_list), max(ts_list)
            with self._locked_transaction() as connection:
                connection.execute(
                    """INSERT OR IGNORE INTO ingest_requests (
                        request_id, received_at_utc, sent_at_utc, source, session_id,
                        capture_mode, points_count, first_point_ts_utc, last_point_ts_utc,
                        user_agent, remote_addr, proxied_ip, ingest_status, http_status,
                        error_category, error_detail, raw_payload_json, raw_payload_reference
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request_id, received_iso, received_iso, source, session_id,
                     "imported", inserted, inserted_first_ts, inserted_last_ts,
                     "import", "", "", "accepted", 202, None, None, "{}", None),
                )
                inserted_so_far = 0
                batch_size = 500
                for index in range(0, len(point_rows), batch_size):
                    batch = point_rows[index : index + batch_size]
                    connection.executemany(
                        """INSERT INTO gps_points (
                            request_id, received_at_utc, sent_at_utc, point_timestamp_utc,
                            latitude, longitude, horizontal_accuracy_m, source, session_id,
                            capture_mode, point_date_local, point_time_local, point_timestamp_local,
                            tile_z10_x, tile_z10_y, tile_z14_x, tile_z14_y, tile_z10_key, tile_z14_key
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        batch,
                    )
                    self._update_point_rollups(connection, batch)
                    self._update_timeline_day_markers(connection, batch)
                    self._update_session_track_rollups(connection, batch)
                    inserted_so_far += len(batch)
                    if progress_callback:
                        progress_callback(
                            {
                                "raw_points": len(points),
                                "processed_points": skipped_total + inserted_so_far,
                                "remaining_points": max(0, inserted - inserted_so_far),
                                "inserted_points": inserted_so_far,
                                "skipped_total": skipped_total,
                            }
                        )
        return {
            "inserted": inserted,
            "skipped_total": skipped_total,
            "invalid_rows": invalid_rows,
            "deduped_in_file": deduped_in_file,
            "already_existing": already_existing,
            "raw_points": len(points),
            "request_id": request_id,
            "first_timestamp_utc": first_ts,
            "last_timestamp_utc": last_ts,
        }

    def get_live_summary(self, *, limit: int) -> dict[str, Any]:
        self._require_ready()
        capped_limit = max(1, min(limit, self.settings.points_page_size_max * 40))
        return {
            "generatedAtUtc": isoformat_utc(datetime.now(timezone.utc)),
            "stats": self.get_stats(),
            "recentPoints": self.list_points(PointFilters(page=1, page_size=capped_limit))["items"],
        }

    def count_points(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        spatial_zoom_hint: int | None = None,
    ) -> int:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        count_query = f"SELECT COUNT(*) AS total FROM gps_points {where_clause}"
        with self._connect() as connection:
            total = connection.execute(count_query, parameters).fetchone()["total"]
        return int(total or 0)

    def latest_point_timestamp(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        spatial_zoom_hint: int | None = None,
    ) -> str | None:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        query = f"SELECT MAX(point_timestamp_utc) AS latest_point_ts_utc FROM gps_points {where_clause}"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if not row:
            return None
        return row["latest_point_ts_utc"]

    def list_points_in_bbox(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float],
        spatial_zoom_hint: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        query = f"""
            SELECT
                id,
                request_id,
                received_at_utc,
                sent_at_utc,
                point_timestamp_utc,
                point_timestamp_local,
                point_date_local,
                point_time_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                session_id,
                source,
                capture_mode
            FROM gps_points
            {where_clause}
            ORDER BY point_timestamp_utc DESC, id DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def list_points_in_bbox_sampled(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float],
        target_limit: int = 2000,
        spatial_zoom_hint: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        total_in_bbox = self.count_points(filters, bbox=bbox, spatial_zoom_hint=spatial_zoom_hint)
        if total_in_bbox <= target_limit:
            return self.list_points_in_bbox(filters, bbox=bbox, spatial_zoom_hint=spatial_zoom_hint)

        stride = max(1, total_in_bbox // target_limit)
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        
        # Sampling logic using row_number() window function
        query = f"""
            SELECT * FROM (
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode,
                    row_number() OVER (ORDER BY point_timestamp_utc DESC, id DESC) as rn
                FROM gps_points
                {where_clause}
            ) WHERE rn % ? = 0 OR rn = 1 OR rn = ?
            ORDER BY point_timestamp_utc DESC, id DESC
        """
        parameters.extend([stride, total_in_bbox])
        
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def list_timeline_points(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 50000,
        spatial_zoom_hint: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        capped_limit = max(1, min(int(limit), 50000))
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        query = f"""
            SELECT
                id,
                point_timestamp_utc,
                point_timestamp_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                session_id,
                source,
                capture_mode
            FROM gps_points
            {where_clause}
            ORDER BY point_timestamp_utc ASC, id ASC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(query, [*parameters, capped_limit]).fetchall()
        return [dict(row) for row in rows]

    def list_points_since(
        self,
        filters: PointFilters,
        *,
        since_utc: str,
        bbox: tuple[float, float, float, float] | None = None,
        spatial_zoom_hint: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        clauses = [] if not where_clause else [where_clause.removeprefix("WHERE ").strip()]
        clauses.append("point_timestamp_utc > ?")
        parameters = [*parameters, since_utc]
        query = f"""
            SELECT
                id,
                request_id,
                received_at_utc,
                sent_at_utc,
                point_timestamp_utc,
                point_timestamp_local,
                point_date_local,
                point_time_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                session_id,
                source,
                capture_mode
            FROM gps_points
            WHERE {' AND '.join(clauses)}
            ORDER BY point_timestamp_utc DESC, id DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def list_heatmap_points(
        self,
        filters: PointFilters,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        spatial_zoom_hint: int | None = None,
    ) -> list[list[float]]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        where_clause, parameters = _append_bbox_filter(where_clause, parameters, bbox, spatial_zoom_hint=spatial_zoom_hint)
        query = f"""
            SELECT
                latitude, longitude, horizontal_accuracy_m
            FROM gps_points
            {where_clause}
            ORDER BY point_timestamp_utc DESC, id DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return rows


    def list_points(self, filters: PointFilters) -> dict[str, Any]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        offset = (filters.page - 1) * filters.page_size

        query = f"""
            SELECT
                id,
                request_id,
                received_at_utc,
                sent_at_utc,
                point_timestamp_utc,
                point_timestamp_local,
                point_date_local,
                point_time_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                session_id,
                source,
                capture_mode
            FROM gps_points
            {where_clause}
            ORDER BY point_timestamp_utc DESC, id DESC
            LIMIT ? OFFSET ?
        """
        count_query = f"SELECT COUNT(*) AS total FROM gps_points {where_clause}"

        with self._connect() as connection:
            total = connection.execute(count_query, parameters).fetchone()["total"]
            rows = connection.execute(query, [*parameters, filters.page_size, offset]).fetchall()

        return {
            "page": filters.page,
            "pageSize": filters.page_size,
            "total": total,
            "items": [dict(row) for row in rows],
        }

    def export_points(self, filters: PointFilters, *, export_format: str) -> tuple[str, str]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        query = f"""
            SELECT
                id,
                request_id,
                received_at_utc,
                sent_at_utc,
                point_timestamp_utc,
                point_timestamp_local,
                point_date_local,
                point_time_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                session_id,
                source,
                capture_mode
            FROM gps_points
            {where_clause}
            ORDER BY point_timestamp_utc DESC, id DESC
        """
        with self._connect() as connection:
            listed = [dict(row) for row in connection.execute(query, parameters).fetchall()]

        if export_format == "json":
            return json.dumps(listed, ensure_ascii=False, indent=2), "application/json"
        if export_format == "geojson":
            features = [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [item["longitude"], item["latitude"]]},
                    "properties": {
                        "id": item["id"],
                        "request_id": item["request_id"],
                        "received_at_utc": item["received_at_utc"],
                        "sent_at_utc": item["sent_at_utc"],
                        "point_timestamp_utc": item["point_timestamp_utc"],
                        "point_timestamp_local": item["point_timestamp_local"],
                        "point_date_local": item["point_date_local"],
                        "point_time_local": item["point_time_local"],
                        "horizontal_accuracy_m": item["horizontal_accuracy_m"],
                        "session_id": item["session_id"],
                        "source": item["source"],
                        "capture_mode": item["capture_mode"],
                    },
                }
                for item in listed
            ]
            return json.dumps(
                {"type": "FeatureCollection", "features": features},
                ensure_ascii=False,
                indent=2,
            ), "application/geo+json"
        if export_format == "ndjson":
            return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in listed), "application/x-ndjson"
        if export_format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "request_id",
                    "received_at_utc",
                    "sent_at_utc",
                    "point_timestamp_utc",
                    "point_timestamp_local",
                    "point_date_local",
                    "point_time_local",
                    "latitude",
                    "longitude",
                    "horizontal_accuracy_m",
                    "session_id",
                    "source",
                    "capture_mode",
                ],
            )
            writer.writeheader()
            writer.writerows(listed)
            return output.getvalue(), "text/csv; charset=utf-8"
        raise ValueError(f"Unsupported export format: {export_format}")

    def summarize_points(self, filters: PointFilters) -> dict[str, Any]:
        self._require_ready()
        fast_rollup = self._try_rollup_summary(filters)
        if fast_rollup is not None:
            return fast_rollup
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="point_timestamp_utc",
            local_date_column="point_date_local",
            local_time_column="point_time_local",
        )
        query = f"""
            SELECT
                COUNT(*) AS total_points,
                MIN(point_timestamp_utc) AS first_point_ts_utc,
                MAX(point_timestamp_utc) AS last_point_ts_utc,
                MIN(latitude) AS min_latitude,
                MAX(latitude) AS max_latitude,
                MIN(longitude) AS min_longitude,
                MAX(longitude) AS max_longitude
            FROM gps_points
            {where_clause}
        """
        with self._connect() as connection:
            row = dict(connection.execute(query, parameters).fetchone())
        total_points = int(row["total_points"] or 0)
        bounding_box = None
        if total_points:
            bounding_box = {
                "minLatitude": float(row["min_latitude"]),
                "maxLatitude": float(row["max_latitude"]),
                "minLongitude": float(row["min_longitude"]),
                "maxLongitude": float(row["max_longitude"]),
            }
        return {
            "totalPoints": total_points,
            "firstPointTsUtc": row["first_point_ts_utc"],
            "lastPointTsUtc": row["last_point_ts_utc"],
            "boundingBox": bounding_box,
        }

    def list_precomputed_timeline_day_markers(self, filters: PointFilters) -> list[dict[str, Any]] | None:
        self._require_ready()
        if filters.time_from or filters.time_to or filters.capture_mode or filters.source or filters.search:
            return None
        scope_type = "session" if filters.session_id else "global"
        scope_key = filters.session_id or "__global__"
        clauses = ["scope_type = ?", "scope_key = ?"]
        parameters: list[Any] = [scope_type, scope_key]
        if filters.date_from:
            clauses.append("point_date_local >= ?")
            parameters.append(filters.date_from)
        if filters.date_to:
            clauses.append("point_date_local <= ?")
            parameters.append(filters.date_to)
        query = f"""
            SELECT point_date_local, first_point_ts_utc, label
            FROM timeline_day_markers
            WHERE {" AND ".join(clauses)}
            ORDER BY first_point_ts_utc ASC, point_date_local ASC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "type": "day",
                "timestampUtc": row["first_point_ts_utc"],
                "label": row["label"],
            }
            for row in rows
        ]

    def list_precomputed_session_stops(
        self,
        filters: PointFilters,
        *,
        stop_radius_m: int,
        stop_min_duration_min: int,
    ) -> list[dict[str, Any]] | None:
        self._require_ready()
        if (
            not filters.session_id
            or filters.date_from
            or filters.date_to
            or filters.time_from
            or filters.time_to
            or filters.capture_mode
            or filters.source
            or filters.search
            or stop_radius_m != _DEFAULT_STOP_RADIUS_M
            or stop_min_duration_min != _DEFAULT_STOP_MIN_DURATION_MIN
        ):
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    latitude,
                    longitude,
                    radius_m,
                    duration_min,
                    start_time_utc,
                    end_time_utc,
                    start_label,
                    end_label,
                    points_count
                FROM session_stop_rollups
                WHERE session_id = ?
                ORDER BY start_time_utc ASC, end_time_utc ASC
                """,
                (filters.session_id,),
            ).fetchall()
        return [
            {
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "radius": int(row["radius_m"]),
                "durationMin": int(row["duration_min"]),
                "startTimeUtc": row["start_time_utc"],
                "endTimeUtc": row["end_time_utc"],
                "startLabel": row["start_label"] or "",
                "endLabel": row["end_label"] or "",
                "pointsCount": int(row["points_count"]),
            }
            for row in rows
        ]

    def list_precomputed_session_daytracks(
        self,
        filters: PointFilters,
        *,
        zoom: int,
        route_time_gap_min: int,
    ) -> list[dict[str, Any]] | None:
        self._require_ready()
        if (
            not filters.session_id
            or filters.date_from
            or filters.date_to
            or filters.time_from
            or filters.time_to
            or filters.capture_mode
            or filters.source
            or filters.search
            or route_time_gap_min != _DEFAULT_ROUTE_TIME_GAP_MIN
        ):
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    point_date_local,
                    color_index,
                    label_latitude,
                    label_longitude,
                    raw_segments_json,
                    points_count
                FROM session_daytrack_rollups
                WHERE session_id = ?
                ORDER BY point_date_local ASC
                """,
                (filters.session_id,),
            ).fetchall()
        return [
            {
                "day": row["point_date_local"],
                "color": _storage_palette_color(int(row["color_index"])),
                "labelPoint": [float(row["label_latitude"]), float(row["label_longitude"])],
                "segments": [
                    _storage_simplify_coords(segment, zoom)
                    for segment in json.loads(row["raw_segments_json"] or "[]")
                ],
                "pointsCount": int(row["points_count"]),
            }
            for row in rows
        ]

    def _try_rollup_summary(self, filters: PointFilters) -> dict[str, Any] | None:
        if (
            filters.date_from
            or filters.date_to
            or filters.time_from
            or filters.time_to
            or filters.capture_mode
            or filters.source
            or filters.search
        ):
            return None
        scope_type = "session" if filters.session_id else "global"
        scope_key = filters.session_id or "__global__"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    total_points,
                    first_point_ts_utc,
                    last_point_ts_utc,
                    min_latitude,
                    max_latitude,
                    min_longitude,
                    max_longitude
                FROM point_rollups
                WHERE scope_type = ? AND scope_key = ?
                """,
                (scope_type, scope_key),
            ).fetchone()
        if not row:
            return None
        row = dict(row)
        total_points = int(row["total_points"] or 0)
        bounding_box = None
        if total_points:
            bounding_box = {
                "minLatitude": float(row["min_latitude"]),
                "maxLatitude": float(row["max_latitude"]),
                "minLongitude": float(row["min_longitude"]),
                "maxLongitude": float(row["max_longitude"]),
            }
        return {
            "totalPoints": total_points,
            "firstPointTsUtc": row["first_point_ts_utc"],
            "lastPointTsUtc": row["last_point_ts_utc"],
            "boundingBox": bounding_box,
        }

    def get_point(self, point_id: int) -> dict[str, Any] | None:
        self._require_ready()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode
                FROM gps_points
                WHERE id = ?
                """,
                (point_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_requests(self, filters: RequestFilters) -> dict[str, Any]:
        self._require_ready()
        where_clause, parameters = _build_shared_filters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            time_from=filters.time_from,
            time_to=filters.time_to,
            session_id=filters.session_id,
            capture_mode=filters.capture_mode,
            source=filters.source,
            search=filters.search,
            time_column="received_at_utc",
            local_date_column=None,
            local_time_column=None,
        )
        if filters.ingest_status:
            if where_clause:
                where_clause += " AND ingest_status = ?"
            else:
                where_clause = "WHERE ingest_status = ?"
            parameters.append(filters.ingest_status)
        offset = (filters.page - 1) * filters.page_size

        query = f"""
            SELECT
                request_id,
                received_at_utc,
                sent_at_utc,
                source,
                session_id,
                capture_mode,
                points_count,
                first_point_ts_utc,
                last_point_ts_utc,
                user_agent,
                remote_addr,
                proxied_ip,
                ingest_status,
                http_status,
                error_category,
                error_detail,
                raw_payload_reference
            FROM ingest_requests
            {where_clause}
            ORDER BY received_at_utc DESC, request_id DESC
            LIMIT ? OFFSET ?
        """
        count_query = f"SELECT COUNT(*) AS total FROM ingest_requests {where_clause}"

        with self._connect() as connection:
            total = connection.execute(count_query, parameters).fetchone()["total"]
            rows = connection.execute(query, [*parameters, filters.page_size, offset]).fetchall()

        return {
            "page": filters.page,
            "pageSize": filters.page_size,
            "total": total,
            "items": [dict(row) for row in rows],
        }

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        self._require_ready()
        with self._connect() as connection:
            request_row = connection.execute(
                """
                SELECT
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    source,
                    session_id,
                    capture_mode,
                    points_count,
                    first_point_ts_utc,
                    last_point_ts_utc,
                    user_agent,
                    remote_addr,
                    proxied_ip,
                    ingest_status,
                    http_status,
                    error_category,
                    error_detail,
                    raw_payload_json,
                    raw_payload_reference
                FROM ingest_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if not request_row:
                return None

            points = connection.execute(
                """
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode
                FROM gps_points
                WHERE request_id = ?
                ORDER BY point_timestamp_utc ASC, id ASC
                """,
                (request_id,),
            ).fetchall()

        result = dict(request_row)
        result["points"] = [dict(row) for row in points]
        result["boundingBox"] = _compute_bounding_box(result["points"])
        result["durationSeconds"] = _duration_seconds(result["first_point_ts_utc"], result["last_point_ts_utc"])
        return result

    def list_sessions(self) -> list[dict[str, Any]]:
        self._require_ready()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    MIN(source) AS source,
                    CASE
                        WHEN COUNT(DISTINCT capture_mode) = 1 THEN MIN(capture_mode)
                        ELSE 'mixed'
                    END AS capture_mode,
                    COUNT(*) AS points_count,
                    COUNT(DISTINCT request_id) AS requests_count,
                    AVG(horizontal_accuracy_m) AS avg_accuracy_m,
                    MIN(point_timestamp_utc) AS first_point_ts_utc,
                    MAX(point_timestamp_utc) AS last_point_ts_utc,
                    MIN(latitude) AS min_latitude,
                    MAX(latitude) AS max_latitude,
                    MIN(longitude) AS min_longitude,
                    MAX(longitude) AS max_longitude
                FROM gps_points
                GROUP BY session_id
                ORDER BY last_point_ts_utc DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> int:
        """Löscht Session inkl. aller Punkte und Ingest-Requests.
        Gibt Anzahl gelöschter GPS-Punkte zurück.
        Stats (Dashboard-Gesamt) werden korrekt aktualisiert weil ingest_requests
        gelöscht wird (FK ON DELETE CASCADE löscht gps_points mit)."""
        self._require_ready()
        with self._locked_transaction() as connection:
            # Punkte vorab zählen für Rückgabewert
            count = connection.execute(
                "SELECT COUNT(*) FROM gps_points WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            # ingest_requests löschen → FK-Cascade löscht gps_points automatisch
            connection.execute(
                "DELETE FROM ingest_requests WHERE session_id = ?", (session_id,)
            )
            connection.execute(
                "DELETE FROM point_rollups WHERE scope_type = 'session' AND scope_key = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM timeline_day_markers WHERE scope_type = 'session' AND scope_key = ?",
                (session_id,),
            )
            connection.execute("DELETE FROM session_stop_rollups WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM session_daytrack_rollups WHERE session_id = ?", (session_id,))
            self._rebuild_global_rollup(connection)
            self._rebuild_global_timeline_day_markers(connection)
            connection.commit()
            # WAL-Checkpoint damit Dateigröße zeitnah reduziert wird
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return count

    def vacuum(self) -> dict[str, Any]:
        """VACUUM: gibt ungenutzten Speicher dauerhaft frei (nicht nur WAL-Checkpoint)."""
        self._require_ready()
        size_before = self.sqlite_path.stat().st_size if self.sqlite_path.exists() else 0
        # VACUUM muss außerhalb einer Transaktion laufen → isolation_level=None
        with self._lock:
            conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("VACUUM")
            finally:
                conn.close()
        size_after = self.sqlite_path.stat().st_size if self.sqlite_path.exists() else 0
        return {"size_before": size_before, "size_after": size_after, "freed_bytes": size_before - size_after}

    def _update_point_rollups(self, connection: sqlite3.Connection, point_rows: list[tuple[Any, ...]]) -> None:
        if not point_rows:
            return
        self._apply_rollup_rows(connection, "global", "__global__", point_rows)
        grouped: dict[str, list[tuple[Any, ...]]] = {}
        for row in point_rows:
            grouped.setdefault(str(row[8]), []).append(row)
        for session_id, rows in grouped.items():
            self._apply_rollup_rows(connection, "session", session_id, rows)

    def _update_timeline_day_markers(self, connection: sqlite3.Connection, point_rows: list[tuple[Any, ...]]) -> None:
        if not point_rows:
            return
        self._apply_timeline_day_marker_rows(connection, "global", "__global__", point_rows)
        grouped: dict[str, list[tuple[Any, ...]]] = {}
        for row in point_rows:
            grouped.setdefault(str(row[8]), []).append(row)
        for session_id, rows in grouped.items():
            self._apply_timeline_day_marker_rows(connection, "session", session_id, rows)

    def _update_session_track_rollups(self, connection: sqlite3.Connection, point_rows: list[tuple[Any, ...]]) -> None:
        if not point_rows:
            return
        session_ids = sorted({str(row[8]) for row in point_rows if row[8]})
        for session_id in session_ids:
            self._rebuild_session_track_rollups(connection, session_id)

    def _apply_rollup_rows(
        self,
        connection: sqlite3.Connection,
        scope_type: str,
        scope_key: str,
        point_rows: list[tuple[Any, ...]],
    ) -> None:
        timestamps = [str(row[3]) for row in point_rows]
        latitudes = [float(row[4]) for row in point_rows]
        longitudes = [float(row[5]) for row in point_rows]
        connection.execute(
            """
            INSERT INTO point_rollups(
                scope_type, scope_key, total_points,
                first_point_ts_utc, last_point_ts_utc,
                min_latitude, max_latitude, min_longitude, max_longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_type, scope_key) DO UPDATE SET
                total_points = point_rollups.total_points + excluded.total_points,
                first_point_ts_utc = CASE
                    WHEN point_rollups.first_point_ts_utc IS NULL THEN excluded.first_point_ts_utc
                    WHEN excluded.first_point_ts_utc < point_rollups.first_point_ts_utc THEN excluded.first_point_ts_utc
                    ELSE point_rollups.first_point_ts_utc
                END,
                last_point_ts_utc = CASE
                    WHEN point_rollups.last_point_ts_utc IS NULL THEN excluded.last_point_ts_utc
                    WHEN excluded.last_point_ts_utc > point_rollups.last_point_ts_utc THEN excluded.last_point_ts_utc
                    ELSE point_rollups.last_point_ts_utc
                END,
                min_latitude = MIN(point_rollups.min_latitude, excluded.min_latitude),
                max_latitude = MAX(point_rollups.max_latitude, excluded.max_latitude),
                min_longitude = MIN(point_rollups.min_longitude, excluded.min_longitude),
                max_longitude = MAX(point_rollups.max_longitude, excluded.max_longitude)
            """,
            (
                scope_type,
                scope_key,
                len(point_rows),
                min(timestamps),
                max(timestamps),
                min(latitudes),
                max(latitudes),
                min(longitudes),
                max(longitudes),
            ),
        )

    def _rebuild_point_rollups(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM point_rollups")
        self._rebuild_global_rollup(connection)
        session_rows = connection.execute(
            """
            SELECT
                session_id,
                COUNT(*) AS total_points,
                MIN(point_timestamp_utc) AS first_point_ts_utc,
                MAX(point_timestamp_utc) AS last_point_ts_utc,
                MIN(latitude) AS min_latitude,
                MAX(latitude) AS max_latitude,
                MIN(longitude) AS min_longitude,
                MAX(longitude) AS max_longitude
            FROM gps_points
            GROUP BY session_id
            """
        ).fetchall()
        for row in session_rows:
            connection.execute(
                """
                INSERT OR REPLACE INTO point_rollups(
                    scope_type, scope_key, total_points,
                    first_point_ts_utc, last_point_ts_utc,
                    min_latitude, max_latitude, min_longitude, max_longitude
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "session",
                    row["session_id"],
                    row["total_points"],
                    row["first_point_ts_utc"],
                    row["last_point_ts_utc"],
                    row["min_latitude"],
                    row["max_latitude"],
                    row["min_longitude"],
                    row["max_longitude"],
                ),
            )

    def _apply_timeline_day_marker_rows(
        self,
        connection: sqlite3.Connection,
        scope_type: str,
        scope_key: str,
        point_rows: list[tuple[Any, ...]],
    ) -> None:
        day_rows: dict[str, str] = {}
        for row in point_rows:
            point_date_local = str(row[10])
            point_ts_utc = str(row[3])
            current = day_rows.get(point_date_local)
            if current is None or point_ts_utc < current:
                day_rows[point_date_local] = point_ts_utc
        connection.executemany(
            """
            INSERT INTO timeline_day_markers(scope_type, scope_key, point_date_local, first_point_ts_utc, label)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(scope_type, scope_key, point_date_local) DO UPDATE SET
                first_point_ts_utc = MIN(timeline_day_markers.first_point_ts_utc, excluded.first_point_ts_utc),
                label = excluded.label
            """,
            [
                (scope_type, scope_key, point_date_local, first_point_ts_utc, point_date_local)
                for point_date_local, first_point_ts_utc in day_rows.items()
            ],
        )

    def _rebuild_timeline_day_markers(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM timeline_day_markers")
        self._rebuild_global_timeline_day_markers(connection)
        session_rows = connection.execute(
            """
            SELECT
                session_id,
                point_date_local,
                MIN(point_timestamp_utc) AS first_point_ts_utc
            FROM gps_points
            GROUP BY session_id, point_date_local
            """
        ).fetchall()
        connection.executemany(
            """
            INSERT OR REPLACE INTO timeline_day_markers(
                scope_type, scope_key, point_date_local, first_point_ts_utc, label
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("session", row["session_id"], row["point_date_local"], row["first_point_ts_utc"], row["point_date_local"])
                for row in session_rows
            ],
        )

    def _rebuild_session_track_rollups(self, connection: sqlite3.Connection, session_id: str) -> None:
        connection.execute("DELETE FROM session_stop_rollups WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM session_daytrack_rollups WHERE session_id = ?", (session_id,))
        points = self._list_session_points_asc(connection, session_id)
        if not points:
            return

        stops = _storage_detect_stops(
            points,
            stop_radius_m=_DEFAULT_STOP_RADIUS_M,
            stop_min_duration_min=_DEFAULT_STOP_MIN_DURATION_MIN,
        )
        if stops:
            connection.executemany(
                """
                INSERT OR REPLACE INTO session_stop_rollups(
                    session_id,
                    start_time_utc,
                    end_time_utc,
                    latitude,
                    longitude,
                    radius_m,
                    duration_min,
                    start_label,
                    end_label,
                    points_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        item["startTimeUtc"],
                        item["endTimeUtc"],
                        item["lat"],
                        item["lon"],
                        item["radius"],
                        item["durationMin"],
                        item["startLabel"],
                        item["endLabel"],
                        item["pointsCount"],
                    )
                    for item in stops
                ],
            )

        daytracks = _storage_build_daytrack_rollups(
            points,
            route_time_gap_min=_DEFAULT_ROUTE_TIME_GAP_MIN,
        )
        if daytracks:
            connection.executemany(
                """
                INSERT OR REPLACE INTO session_daytrack_rollups(
                    session_id,
                    point_date_local,
                    color_index,
                    label_latitude,
                    label_longitude,
                    raw_segments_json,
                    points_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        item["day"],
                        item["colorIndex"],
                        item["labelLat"],
                        item["labelLon"],
                        json.dumps(item["rawSegments"], separators=(",", ":")),
                        item["pointsCount"],
                    )
                    for item in daytracks
                ],
            )

    def _rebuild_global_timeline_day_markers(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM timeline_day_markers WHERE scope_type = 'global' AND scope_key = '__global__'"
        )
        rows = connection.execute(
            """
            SELECT
                point_date_local,
                MIN(point_timestamp_utc) AS first_point_ts_utc
            FROM gps_points
            GROUP BY point_date_local
            """
        ).fetchall()
        connection.executemany(
            """
            INSERT OR REPLACE INTO timeline_day_markers(
                scope_type, scope_key, point_date_local, first_point_ts_utc, label
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("global", "__global__", row["point_date_local"], row["first_point_ts_utc"], row["point_date_local"])
                for row in rows
            ],
        )

    def _rebuild_all_session_track_rollups(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM session_stop_rollups")
        connection.execute("DELETE FROM session_daytrack_rollups")
        rows = connection.execute("SELECT DISTINCT session_id FROM gps_points ORDER BY session_id ASC").fetchall()
        for row in rows:
            self._rebuild_session_track_rollups(connection, str(row["session_id"]))

    def _list_session_points_asc(self, connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
                id,
                point_timestamp_utc,
                point_timestamp_local,
                point_date_local,
                latitude,
                longitude,
                horizontal_accuracy_m,
                source,
                capture_mode,
                request_id
            FROM gps_points
            WHERE session_id = ?
            ORDER BY point_timestamp_utc ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_gps_points_tile_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(gps_points)").fetchall()
        }
        for column_name in ("tile_z10_x", "tile_z10_y", "tile_z14_x", "tile_z14_y", "tile_z10_key", "tile_z14_key"):
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE gps_points ADD COLUMN {column_name} INTEGER")

    def _rebuild_spatial_tiles(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, latitude, longitude
            FROM gps_points
            WHERE tile_z10_x IS NULL OR tile_z10_y IS NULL OR tile_z14_x IS NULL OR tile_z14_y IS NULL
               OR tile_z10_key IS NULL OR tile_z14_key IS NULL
            """
        ).fetchall()
        if not rows:
            return
        connection.executemany(
            """
            UPDATE gps_points
            SET tile_z10_x = ?, tile_z10_y = ?, tile_z14_x = ?, tile_z14_y = ?, tile_z10_key = ?, tile_z14_key = ?
            WHERE id = ?
            """,
            [
                _tile_columns_for_row(float(row["latitude"]), float(row["longitude"]), int(row["id"]))
                for row in rows
            ],
        )

    def _rebuild_global_rollup(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_points,
                MIN(point_timestamp_utc) AS first_point_ts_utc,
                MAX(point_timestamp_utc) AS last_point_ts_utc,
                MIN(latitude) AS min_latitude,
                MAX(latitude) AS max_latitude,
                MIN(longitude) AS min_longitude,
                MAX(longitude) AS max_longitude
            FROM gps_points
            """
        ).fetchone()
        if not row or not int(row["total_points"] or 0):
            connection.execute(
                "DELETE FROM point_rollups WHERE scope_type = 'global' AND scope_key = '__global__'"
            )
            return
        connection.execute(
            """
            INSERT OR REPLACE INTO point_rollups(
                scope_type, scope_key, total_points,
                first_point_ts_utc, last_point_ts_utc,
                min_latitude, max_latitude, min_longitude, max_longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "global",
                "__global__",
                row["total_points"],
                row["first_point_ts_utc"],
                row["last_point_ts_utc"],
                row["min_latitude"],
                row["max_latitude"],
                row["min_longitude"],
                row["max_longitude"],
            ),
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        self._require_ready()
        with self._connect() as connection:
            summary = connection.execute(
                """
                SELECT
                    session_id,
                    MIN(source) AS source,
                    CASE
                        WHEN COUNT(DISTINCT capture_mode) = 1 THEN MIN(capture_mode)
                        ELSE 'mixed'
                    END AS capture_mode,
                    COUNT(*) AS points_count,
                    COUNT(DISTINCT request_id) AS requests_count,
                    AVG(horizontal_accuracy_m) AS avg_accuracy_m,
                    MIN(point_timestamp_utc) AS first_point_ts_utc,
                    MAX(point_timestamp_utc) AS last_point_ts_utc,
                    MIN(latitude) AS min_latitude,
                    MAX(latitude) AS max_latitude,
                    MIN(longitude) AS min_longitude,
                    MAX(longitude) AS max_longitude
                FROM gps_points
                WHERE session_id = ?
                GROUP BY session_id
                """,
                (session_id,),
            ).fetchone()
            if not summary:
                return None
            points = connection.execute(
                """
                SELECT
                    id,
                    request_id,
                    received_at_utc,
                    sent_at_utc,
                    point_timestamp_utc,
                    point_timestamp_local,
                    point_date_local,
                    point_time_local,
                    latitude,
                    longitude,
                    horizontal_accuracy_m,
                    session_id,
                    source,
                    capture_mode
                FROM gps_points
                WHERE session_id = ?
                ORDER BY point_timestamp_utc ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
            related_requests = connection.execute(
                """
                SELECT
                    request_id,
                    received_at_utc,
                    ingest_status,
                    http_status,
                    error_category,
                    error_detail,
                    points_count
                FROM ingest_requests
                WHERE session_id = ?
                ORDER BY received_at_utc DESC
                """,
                (session_id,),
            ).fetchall()

        result = dict(summary)
        result["points"] = [dict(row) for row in points]
        result["requests"] = [dict(row) for row in related_requests]
        result["boundingBox"] = _compute_bounding_box(result["points"])
        result["durationSeconds"] = _duration_seconds(result["first_point_ts_utc"], result["last_point_ts_utc"])
        return result

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _prepare_filesystem(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        if self.settings.raw_payload_ndjson_enabled:
            self.raw_ndjson_path.parent.mkdir(parents=True, exist_ok=True)

    def _is_writable(self) -> bool:
        try:
            self._prepare_filesystem()
            probe_paths = (
                self.settings.data_dir / ".receiver-write-test",
                self.sqlite_path.parent / ".receiver-sqlite-write-test",
            )
            for probe_path in probe_paths:
                probe_path.write_text("ok", encoding="utf-8")
                probe_path.unlink(missing_ok=True)
            with self.sqlite_path.open("a", encoding="utf-8"):
                pass
            if self.settings.raw_payload_ndjson_enabled:
                with self.raw_ndjson_path.open("a", encoding="utf-8"):
                    pass
            return True
        except Exception as exc:
            self._last_error = str(exc)
            return False

    def _require_ready(self) -> None:
        state = self.readiness()
        if not state.is_ready:
            raise StorageNotReadyError(state.message)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _locked_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            with self._connect() as connection:
                try:
                    yield connection
                    connection.commit()
                except sqlite3.DatabaseError as exc:
                    connection.rollback()
                    raise StorageWriteError(str(exc)) from exc

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingest_requests (
                request_id TEXT PRIMARY KEY,
                received_at_utc TEXT NOT NULL,
                sent_at_utc TEXT,
                source TEXT,
                session_id TEXT,
                capture_mode TEXT,
                points_count INTEGER NOT NULL DEFAULT 0,
                first_point_ts_utc TEXT,
                last_point_ts_utc TEXT,
                user_agent TEXT,
                remote_addr TEXT,
                proxied_ip TEXT,
                ingest_status TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                error_category TEXT,
                error_detail TEXT,
                raw_payload_json TEXT,
                raw_payload_reference TEXT
            );

            CREATE TABLE IF NOT EXISTS gps_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL REFERENCES ingest_requests(request_id) ON DELETE CASCADE,
                received_at_utc TEXT NOT NULL,
                sent_at_utc TEXT NOT NULL,
                point_timestamp_utc TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                horizontal_accuracy_m REAL NOT NULL,
                source TEXT NOT NULL,
                session_id TEXT NOT NULL,
                capture_mode TEXT NOT NULL,
                point_date_local TEXT NOT NULL,
                point_time_local TEXT NOT NULL,
                point_timestamp_local TEXT NOT NULL,
                tile_z10_x INTEGER,
                tile_z10_y INTEGER,
                tile_z14_x INTEGER,
                tile_z14_y INTEGER,
                tile_z10_key INTEGER,
                tile_z14_key INTEGER
            );

            CREATE TABLE IF NOT EXISTS point_rollups (
                scope_type TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                total_points INTEGER NOT NULL DEFAULT 0,
                first_point_ts_utc TEXT,
                last_point_ts_utc TEXT,
                min_latitude REAL,
                max_latitude REAL,
                min_longitude REAL,
                max_longitude REAL,
                PRIMARY KEY (scope_type, scope_key)
            );

            CREATE TABLE IF NOT EXISTS timeline_day_markers (
                scope_type TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                point_date_local TEXT NOT NULL,
                first_point_ts_utc TEXT NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY (scope_type, scope_key, point_date_local)
            );

            CREATE TABLE IF NOT EXISTS session_stop_rollups (
                session_id TEXT NOT NULL,
                start_time_utc TEXT NOT NULL,
                end_time_utc TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_m INTEGER NOT NULL,
                duration_min INTEGER NOT NULL,
                start_label TEXT NOT NULL,
                end_label TEXT NOT NULL,
                points_count INTEGER NOT NULL,
                PRIMARY KEY (session_id, start_time_utc, end_time_utc)
            );

            CREATE TABLE IF NOT EXISTS session_daytrack_rollups (
                session_id TEXT NOT NULL,
                point_date_local TEXT NOT NULL,
                color_index INTEGER NOT NULL,
                label_latitude REAL NOT NULL,
                label_longitude REAL NOT NULL,
                raw_segments_json TEXT NOT NULL,
                points_count INTEGER NOT NULL,
                PRIMARY KEY (session_id, point_date_local)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS gps_points_rtree USING rtree(
                id,
                min_lon, max_lon,
                min_lat, max_lat
            );

            CREATE TRIGGER IF NOT EXISTS trg_gps_points_rtree_insert
            AFTER INSERT ON gps_points
            BEGIN
                INSERT OR REPLACE INTO gps_points_rtree(id, min_lon, max_lon, min_lat, max_lat)
                VALUES (NEW.id, NEW.longitude, NEW.longitude, NEW.latitude, NEW.latitude);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_gps_points_rtree_delete
            AFTER DELETE ON gps_points
            BEGIN
                DELETE FROM gps_points_rtree WHERE id = OLD.id;
            END;

            -- Indices for Requests
            CREATE INDEX IF NOT EXISTS idx_ingest_requests_received_at
                ON ingest_requests(received_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_ingest_requests_session
                ON ingest_requests(session_id, received_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_ingest_requests_status
                ON ingest_requests(ingest_status, received_at_utc DESC);

            -- Indices for GPS Points (Performance for Dashboard and Exports)
            CREATE INDEX IF NOT EXISTS idx_gps_points_timestamp
                ON gps_points(point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_timestamp_order
                ON gps_points(point_timestamp_utc DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_session_timestamp
                ON gps_points(session_id, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_session_timestamp_order
                ON gps_points(session_id, point_timestamp_utc DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_request
                ON gps_points(request_id);
            CREATE INDEX IF NOT EXISTS idx_gps_points_coords
                ON gps_points(latitude, longitude);
            CREATE INDEX IF NOT EXISTS idx_gps_points_lat_lon_timestamp
                ON gps_points(latitude, longitude, point_timestamp_utc DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_lon_lat_timestamp
                ON gps_points(longitude, latitude, point_timestamp_utc DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_mode
                ON gps_points(capture_mode, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_source
                ON gps_points(source, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_date_local
                ON gps_points(point_date_local DESC, point_time_local DESC);
            CREATE INDEX IF NOT EXISTS idx_session_stop_rollups_session
                ON session_stop_rollups(session_id, start_time_utc ASC, end_time_utc ASC);
            CREATE INDEX IF NOT EXISTS idx_session_daytrack_rollups_session
                ON session_daytrack_rollups(session_id, point_date_local ASC);
            """
        )
        self._ensure_gps_points_tile_columns(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_gps_points_tile_z10 ON gps_points(tile_z10_x, tile_z10_y, point_timestamp_utc DESC, id DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_gps_points_tile_z14 ON gps_points(tile_z14_x, tile_z14_y, point_timestamp_utc DESC, id DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_gps_points_tile_z10_key ON gps_points(tile_z10_key, point_timestamp_utc DESC, id DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_gps_points_tile_z14_key ON gps_points(tile_z14_key, point_timestamp_utc DESC, id DESC)"
        )
        rtree_ready = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("gps_points_rtree_ready_v1",),
        ).fetchone()
        if not rtree_ready:
            connection.execute(
                """
                INSERT OR REPLACE INTO gps_points_rtree(id, min_lon, max_lon, min_lat, max_lat)
                SELECT id, longitude, longitude, latitude, latitude
                FROM gps_points
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("gps_points_rtree_ready_v1", "1"),
            )
        rollups_ready = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("point_rollups_ready_v1",),
        ).fetchone()
        if not rollups_ready:
            self._rebuild_point_rollups(connection)
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("point_rollups_ready_v1", "1"),
            )
        timeline_markers_ready = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("timeline_day_markers_ready_v1",),
        ).fetchone()
        if not timeline_markers_ready:
            self._rebuild_timeline_day_markers(connection)
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("timeline_day_markers_ready_v1", "1"),
            )
        spatial_tiles_ready = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("gps_points_tiles_ready_v2",),
        ).fetchone()
        if not spatial_tiles_ready:
            self._rebuild_spatial_tiles(connection)
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("gps_points_tiles_ready_v2", "1"),
            )
        session_track_rollups_ready = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("session_track_rollups_ready_v1",),
        ).fetchone()
        if not session_track_rollups_ready:
            self._rebuild_all_session_track_rollups(connection)
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("session_track_rollups_ready_v1", "1"),
            )

    def _maybe_import_legacy_ndjson(self, connection: sqlite3.Connection) -> None:
        legacy_path = self.settings.legacy_request_ndjson_path
        if legacy_path == self.raw_ndjson_path:
            return
        if not legacy_path.exists():
            return

        already_imported = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("legacy_import_completed",),
        ).fetchone()
        if already_imported:
            return

        total_requests = connection.execute("SELECT COUNT(*) AS total FROM ingest_requests").fetchone()["total"]
        if total_requests:
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
                ("legacy_import_completed", "skipped_existing_data"),
            )
            connection.commit()
            return

        imported = 0
        with legacy_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw_line = line.strip()
                if not raw_line:
                    continue
                parsed = json.loads(raw_line)
                payload = LiveLocationRequest.model_validate(parsed)
                request_id = f"legacy-{line_number:08d}-{sha1(raw_line.encode('utf-8')).hexdigest()[:10]}"
                received_at = payload.sentAt.astimezone(timezone.utc)
                metadata = RequestMetadata(
                    request_id=request_id,
                    received_at_utc=received_at,
                    remote_addr="",
                    proxied_ip="",
                    user_agent="legacy-import",
                    request_path="/live-location",
                    request_method="POST",
                )
                self.ingest_success(
                    payload=payload,
                    metadata=metadata,
                    raw_payload_text=raw_line,
                )
                imported += 1

        connection.execute(
            "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES(?, ?)",
            ("legacy_import_completed", str(imported)),
        )
        connection.commit()

    def _append_raw_payload(self, *, request_id: str, received_at_utc: datetime, payload_json: dict[str, Any]) -> str | None:
        if not self.settings.raw_payload_ndjson_enabled:
            return None

        line = json.dumps(
            {
                "requestId": request_id,
                "receivedAtUtc": isoformat_utc(received_at_utc),
                "payload": payload_json,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        try:
            with self._lock:
                self.raw_ndjson_path.parent.mkdir(parents=True, exist_ok=True)
                with self.raw_ndjson_path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
            return str(self.raw_ndjson_path)
        except OSError as exc:
            raise StorageWriteError(str(exc)) from exc

