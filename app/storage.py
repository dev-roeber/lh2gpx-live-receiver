from __future__ import annotations

import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from threading import Lock
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from .config import Settings
from .models import LiveLocationRequest, PointFilters, RequestFilters, RequestMetadata, payload_to_json


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
                    point_timestamp_local
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                point_rows,
            )

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
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    SUM(CASE WHEN ingest_status = 'accepted' THEN 1 ELSE 0 END) AS accepted_requests,
                    SUM(CASE WHEN ingest_status != 'accepted' THEN 1 ELSE 0 END) AS failed_requests,
                    SUM(points_count) AS total_points,
                    MAX(CASE WHEN ingest_status = 'accepted' THEN received_at_utc END) AS last_success_at,
                    MAX(CASE WHEN ingest_status != 'accepted' THEN received_at_utc END) AS last_failure_at,
                    COUNT(DISTINCT CASE WHEN ingest_status = 'accepted' THEN session_id END) AS total_sessions
                FROM ingest_requests
                """
            ).fetchone()

            since_24h = isoformat_utc(datetime.now(timezone.utc) - timedelta(hours=24))
            since_7d = isoformat_utc(datetime.now(timezone.utc) - timedelta(days=7))

            period_rows = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN received_at_utc >= ? THEN points_count ELSE 0 END) AS points_24h,
                    SUM(CASE WHEN received_at_utc >= ? THEN points_count ELSE 0 END) AS points_7d,
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_24h,
                    SUM(CASE WHEN received_at_utc >= ? THEN 1 ELSE 0 END) AS requests_7d
                FROM ingest_requests
                WHERE ingest_status = 'accepted'
                """,
                (since_24h, since_7d, since_24h, since_7d),
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
            "totals": dict(totals),
            "periods": dict(period_rows),
            "pointsPerDay": points_per_day,
            "pointsPerSession": points_per_session,
        }

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
        listed = self.list_points(
            PointFilters(
                date_from=filters.date_from,
                date_to=filters.date_to,
                session_id=filters.session_id,
                capture_mode=filters.capture_mode,
                source=filters.source,
                search=filters.search,
                page=1,
                page_size=self.settings.points_page_size_max * 100,
            )
        )["items"]

        if export_format == "json":
            return json.dumps(listed, ensure_ascii=False, indent=2), "application/json"
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
                    source,
                    capture_mode,
                    COUNT(*) AS points_count,
                    MIN(point_timestamp_utc) AS first_point_ts_utc,
                    MAX(point_timestamp_utc) AS last_point_ts_utc,
                    MIN(latitude) AS min_latitude,
                    MAX(latitude) AS max_latitude,
                    MIN(longitude) AS min_longitude,
                    MAX(longitude) AS max_longitude
                FROM gps_points
                GROUP BY session_id, source, capture_mode
                ORDER BY last_point_ts_utc DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        self._require_ready()
        with self._connect() as connection:
            summary = connection.execute(
                """
                SELECT
                    session_id,
                    source,
                    capture_mode,
                    COUNT(*) AS points_count,
                    MIN(point_timestamp_utc) AS first_point_ts_utc,
                    MAX(point_timestamp_utc) AS last_point_ts_utc,
                    MIN(latitude) AS min_latitude,
                    MAX(latitude) AS max_latitude,
                    MIN(longitude) AS min_longitude,
                    MAX(longitude) AS max_longitude
                FROM gps_points
                WHERE session_id = ?
                GROUP BY session_id, source, capture_mode
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
            probe_path = self.settings.data_dir / ".receiver-write-test"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink(missing_ok=True)
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
                point_timestamp_local TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ingest_requests_received_at
                ON ingest_requests(received_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_ingest_requests_session
                ON ingest_requests(session_id, received_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_ingest_requests_status
                ON ingest_requests(ingest_status, received_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_timestamp
                ON gps_points(point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_session
                ON gps_points(session_id, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_mode
                ON gps_points(capture_mode, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_source
                ON gps_points(source, point_timestamp_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_gps_points_date_local
                ON gps_points(point_date_local DESC, point_time_local DESC);
            """
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
        if local_date_column:
            clauses.append(f"{local_date_column} >= ?")
            parameters.append(date_from)
        else:
            clauses.append(f"{time_column} >= ?")
            parameters.append(_normalize_datetime_filter(date_from, end_of_day=False))
    if date_to:
        if local_date_column:
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


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()
