from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import platform
import secrets
import time
from base64 import b64decode
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from secrets import compare_digest
from typing import Any
from urllib.parse import parse_qs, urlencode
from urllib.request import urlopen
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for connection in dead_connections:
            self.disconnect(connection)

manager = ConnectionManager()
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings
from .import_parsers import ImportError as GpsImportError, parse_file_report as parse_import_file_report
from .models import LiveLocationRequest, PointFilters, RequestFilters, RequestMetadata
from .storage import ReceiverStorage, StorageError, isoformat_utc


LOGGER = logging.getLogger("lh2gpx_live_receiver")
APP_VERSION = "0.4.0"

_SESSION_COOKIE = "lh2gpx_session"
_SESSION_MAX_AGE = 7 * 24 * 3600  # 7 Tage


class _LoginRequired(Exception):
    """Raised by _require_admin_access for HTML dashboard routes that need a login redirect."""
ROOT_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT_DIR / "docs"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
NAV_GROUPS = [
    {
        "title": "Übersicht",
        "items": [
            {"key": "dashboard", "label": "Übersicht", "href": "/dashboard"},
            {"key": "map", "label": "Karte", "href": "/dashboard/map"},
            {"key": "import", "label": "Import", "href": "/dashboard/import"},
            {"key": "live_status", "label": "Receiver-Status", "href": "/dashboard/live-status"},
            {"key": "activity", "label": "Aktivität", "href": "/dashboard/activity"},
        ],
    },
    {
        "title": "Daten",
        "items": [
            {"key": "requests", "label": "Requests", "href": "/dashboard/requests"},
            {"key": "sessions", "label": "Sessions", "href": "/dashboard/sessions"},
            {"key": "points", "label": "Punkte", "href": "/dashboard/points"},
            {"key": "exports", "label": "Exporte", "href": "/dashboard/exports"},
        ],
    },
    {
        "title": "Betrieb & Sicherheit",
        "items": [
            {"key": "security", "label": "Sicherheit", "href": "/dashboard/security"},
            {"key": "storage", "label": "Speicher", "href": "/dashboard/storage"},
            {"key": "config", "label": "Konfiguration", "href": "/dashboard/config"},
            {"key": "system", "label": "System", "href": "/dashboard/system"},
        ],
    },
    {
        "title": "Hilfe",
        "items": [
            {"key": "troubleshooting", "label": "Fehlerbehebung", "href": "/dashboard/troubleshooting"},
            {"key": "open_items", "label": "Offene Punkte", "href": "/dashboard/open-items"},
        ],
    },
]


def short_id(value: str, length: int = 8) -> str:
    """Kürze lange IDs mit Ellipsis am Ende."""
    return value[:length] + "…" if value and len(value) > length else value


class SimpleRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = limit_per_minute
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        if self.limit_per_minute <= 0:
            return True
        now = time.time()
        bucket = self._buckets[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= self.limit_per_minute:
            return False
        bucket.append(now)
        return True


_POINTS_CACHE: dict[str, tuple[float, str, bytes]] = {}  # key → (ts, etag, body)
_POINTS_CACHE_TTL = 5.0  # Sekunden
_MAP_META_CACHE: dict[str, tuple[float, str, bytes]] = {}
_MAP_META_CACHE_TTL = 5.0
_MAP_DATA_CACHE: dict[str, tuple[float, str, bytes]] = {}
_MAP_DATA_CACHE_TTL = 2.0
_HEATMAP_LAYER_CACHE: dict[str, tuple[float, list[list[float]]]] = {}
_HEATMAP_LAYER_CACHE_TTL = 15.0
_TRACK_CONTEXT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TRACK_CONTEXT_CACHE_TTL = 15.0
_TRACK_LAYER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TRACK_LAYER_CACHE_TTL = 8.0
_TIMELINE_PREVIEW_CACHE: dict[str, tuple[float, str, bytes]] = {}
_TIMELINE_PREVIEW_CACHE_TTL = 5.0
_MAP_DATA_PAGE_SIZE_MAX = 20_000
_SNAP_CACHE: dict[str, tuple[float, list[list[float]] | None]] = {}
_SNAP_CACHE_TTL = 300.0
_POINTS_CACHE_MAX = 250
_BODY_CACHE_MAX = 250
_LAYER_CACHE_MAX = 300
_SNAP_CACHE_MAX = 500

_import_tasks: dict[str, dict] = {}  # task_id → {status, ...}


def _cache_get(cache: dict[str, tuple[Any, ...]], key: str, *, ttl: float) -> tuple[Any, ...] | None:
    cached = cache.get(key)
    if not cached:
        return None
    if (time.time() - float(cached[0])) >= ttl:
        cache.pop(key, None)
        return None
    cache.pop(key, None)
    cache[key] = cached
    return cached


def _cache_put(
    cache: dict[str, tuple[Any, ...]],
    key: str,
    value: tuple[Any, ...],
    *,
    ttl: float,
    max_items: int,
) -> None:
    cache.pop(key, None)
    cache[key] = value
    cutoff = time.time() - ttl
    for cache_key in [cache_key for cache_key, cache_value in cache.items() if float(cache_value[0]) < cutoff]:
        cache.pop(cache_key, None)
    while len(cache) > max_items:
        cache.pop(next(iter(cache)))


def _summarize_import_tasks() -> dict[str, Any]:
    active_tasks = [
        {"task_id": task_id, **task}
        for task_id, task in _import_tasks.items()
        if task.get("status") in {"queued", "parsing", "inserting"}
    ]
    if not active_tasks:
        return {
            "allProcessed": True,
            "activeTasks": 0,
            "queuedTasks": 0,
            "parsingTasks": 0,
            "insertingTasks": 0,
            "knownTotalPoints": 0,
            "processedPoints": 0,
            "remainingPoints": 0,
            "unknownTasks": 0,
            "etaSeconds": 0,
            "statusLabel": "Alle verfügbaren Serverdaten verarbeitet",
        }

    queued_tasks = sum(1 for task in active_tasks if task.get("status") == "queued")
    parsing_tasks = sum(1 for task in active_tasks if task.get("status") == "parsing")
    inserting_tasks = sum(1 for task in active_tasks if task.get("status") == "inserting")
    known_total_points = 0
    processed_points = 0
    remaining_points = 0
    unknown_tasks = 0
    eta_values: list[float] = []

    for task in active_tasks:
        metrics = task.get("metrics") or {}
        raw_points = metrics.get("rawPoints")
        if raw_points in {None, ""}:
            unknown_tasks += 1
            continue
        raw_points = int(raw_points)
        processed = int(metrics.get("processedPoints") or 0)
        remaining = int(metrics.get("remainingPoints") or max(0, raw_points - processed))
        known_total_points += raw_points
        processed_points += processed
        remaining_points += remaining
        eta_seconds = metrics.get("estimatedRemainingSeconds")
        if isinstance(eta_seconds, (int, float)) and eta_seconds > 0:
            eta_values.append(float(eta_seconds))

    if inserting_tasks:
        status_label = "Server verarbeitet noch Daten"
    elif parsing_tasks:
        status_label = "Server analysiert Upload-Daten"
    else:
        status_label = "Server wartet auf Verarbeitung"

    return {
        "allProcessed": False,
        "activeTasks": len(active_tasks),
        "queuedTasks": queued_tasks,
        "parsingTasks": parsing_tasks,
        "insertingTasks": inserting_tasks,
        "knownTotalPoints": known_total_points,
        "processedPoints": processed_points,
        "remainingPoints": remaining_points,
        "unknownTasks": unknown_tasks,
        "etaSeconds": round(sum(eta_values), 1) if eta_values else None,
        "statusLabel": status_label,
    }


async def _run_import_task(task_id: str, filename: str, data: bytes, storage: "ReceiverStorage") -> None:
    started_at = time.perf_counter()
    try:
        _import_tasks[task_id].update({"status": "parsing", "updated_at": isoformat_utc(datetime.now(timezone.utc))})
        parse_started_at = time.perf_counter()
        parse_report = await asyncio.to_thread(parse_import_file_report, filename, data)
        points = parse_report["points"]
        parse_duration_ms = round((time.perf_counter() - parse_started_at) * 1000, 2)
        _import_tasks[task_id].update(
            {
                "status": "inserting",
                "updated_at": isoformat_utc(datetime.now(timezone.utc)),
                "detected_format": parse_report.get("detected_format", "unknown"),
                "total": len(points),
                "metrics": {
                    "rawPoints": len(points),
                    "parseDurationMs": parse_duration_ms,
                    "archiveEntriesTotal": parse_report.get("archive_entries_total"),
                    "archiveEntriesUsed": parse_report.get("archive_entries_used"),
                    "archiveEntriesFailed": parse_report.get("archive_entries_failed"),
                },
                "warnings": parse_report.get("warnings", []),
            }
        )
        import_id = str(uuid4())
        session_id = f"import-{import_id[:8]}"
        insert_started_at = time.perf_counter()
        def report_import_progress(progress: dict[str, Any]) -> None:
            task = _import_tasks.get(task_id)
            if not task:
                return
            metrics = dict(task.get("metrics") or {})
            raw_points = int(progress.get("raw_points") or metrics.get("rawPoints") or len(points))
            processed_points = int(progress.get("processed_points") or 0)
            remaining_points = max(0, int(progress.get("remaining_points") or max(0, raw_points - processed_points)))
            elapsed_seconds = max(time.perf_counter() - insert_started_at, 0.001)
            rows_per_second = round(processed_points / elapsed_seconds, 2) if processed_points > 0 else None
            eta_seconds = round(remaining_points / rows_per_second, 1) if rows_per_second and remaining_points > 0 else 0 if remaining_points == 0 else None
            metrics.update(
                {
                    "rawPoints": raw_points,
                    "processedPoints": processed_points,
                    "remainingPoints": remaining_points,
                    "insertedPoints": int(progress.get("inserted_points") or 0),
                    "progressPercent": round((processed_points / raw_points) * 100, 1) if raw_points > 0 else 100.0,
                    "rowsPerSecond": rows_per_second,
                    "estimatedRemainingSeconds": eta_seconds,
                    "skippedTotal": int(progress.get("skipped_total") or metrics.get("skippedTotal") or 0),
                }
            )
            task.update(
                {
                    "updated_at": isoformat_utc(datetime.now(timezone.utc)),
                    "metrics": metrics,
                }
            )

        result = await asyncio.to_thread(
            lambda: storage.import_points(
                points,
                source=f"import:{filename}",
                session_id=session_id,
                request_id=import_id,
                progress_callback=report_import_progress,
            )
        )
        insert_duration_ms = round((time.perf_counter() - insert_started_at) * 1000, 2)
        _import_tasks[task_id] = {
            "status": "done",
            "filename": filename,
            "file_size_bytes": len(data),
            "detected_format": parse_report.get("detected_format", "unknown"),
            "created_at": _import_tasks[task_id].get("created_at"),
            "updated_at": isoformat_utc(datetime.now(timezone.utc)),
            "inserted": result["inserted"],
            "skipped": result["skipped_total"],
            "session_id": session_id,
            "warnings": parse_report.get("warnings", []),
            "metrics": {
                "rawPoints": result["raw_points"],
                "invalidRows": result["invalid_rows"],
                "dedupedInFile": result["deduped_in_file"],
                "alreadyExisting": result["already_existing"],
                "inserted": result["inserted"],
                "skippedTotal": result["skipped_total"],
                "processedPoints": result["raw_points"],
                "remainingPoints": 0,
                "progressPercent": 100.0,
                "rowsPerSecond": round(result["raw_points"] / max(time.perf_counter() - insert_started_at, 0.001), 2) if result["raw_points"] else None,
                "estimatedRemainingSeconds": 0,
                "firstTimestampUtc": result["first_timestamp_utc"],
                "lastTimestampUtc": result["last_timestamp_utc"],
                "parseDurationMs": parse_duration_ms,
                "insertDurationMs": insert_duration_ms,
                "totalDurationMs": round((time.perf_counter() - started_at) * 1000, 2),
                "archiveEntriesTotal": parse_report.get("archive_entries_total"),
                "archiveEntriesUsed": parse_report.get("archive_entries_used"),
                "archiveEntriesFailed": parse_report.get("archive_entries_failed"),
            },
        }
    except GpsImportError as e:
        _import_tasks[task_id] = {
            "status": "error",
            "filename": filename,
            "file_size_bytes": len(data),
            "updated_at": isoformat_utc(datetime.now(timezone.utc)),
            "error": str(e),
            "error_category": "parse_error",
        }
    except Exception as e:
        _import_tasks[task_id] = {
            "status": "error",
            "filename": filename,
            "file_size_bytes": len(data),
            "updated_at": isoformat_utc(datetime.now(timezone.utc)),
            "error": f"Interner Fehler: {type(e).__name__}: {e}",
            "error_category": "internal_error",
        }
    finally:
        asyncio.get_running_loop().call_later(300, _import_tasks.pop, task_id, None)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    _configure_logging(resolved_settings.log_level)

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    templates.env.globals.update(
        format_timestamp=lambda value: _timestamp_summary(value, resolved_settings.local_timezone),
        relative_time=_relative_time,
        format_duration=_format_duration,
        format_bytes=_format_bytes,
        format_percent=_format_percent,
        status_tone=_status_tone,
        short_id=short_id,
    )

    app = FastAPI(title="LH2GPX Live Location Receiver", version=APP_VERSION)
    app.state.settings = resolved_settings
    app.state.storage = ReceiverStorage(resolved_settings)
    app.state.storage.startup()
    app.state.rate_limiter = SimpleRateLimiter(resolved_settings.rate_limit_requests_per_minute)
    app.state.session_signing_key = _build_session_signing_key(resolved_settings)
    app.state.inline_import_tasks = False
    app.state.started_at_utc = datetime.now(timezone.utc)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        request.state.request_started_at = time.perf_counter()
        request.state.received_at_utc = datetime.now(timezone.utc)
        request.state.remote_addr = _direct_remote_addr(request)
        request.state.proxied_ip = _proxied_ip(request, _settings(request).trust_proxy_headers)
        request.state.user_agent = request.headers.get("user-agent", "")
        request.state.log_fields = {}
        request.state.raw_body_text = ""

        if request.method.upper() == "POST" and request.url.path == "/live-location":
            raw_body = await request.body()
            request.state.raw_body_text = raw_body.decode("utf-8", errors="replace")
            max_bytes = _settings(request).request_body_max_bytes
            if len(raw_body) > max_bytes:
                response = _json_error(
                    request=request,
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body exceeds {max_bytes} bytes.",
                    error_category="payload_too_large",
                )
                await _record_failure(
                    request=request,
                    http_status=response.status_code,
                    error_category="payload_too_large",
                    error_detail="Request body exceeded configured size limit.",
                )
                return response

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": raw_body, "more_body": False}

            request = Request(request.scope, receive)

        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                json.dumps(
                    {
                        "event": "request_exception",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
            raise

        response.headers["X-Request-ID"] = request_id
        _log_request(
            request=request,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - request.state.request_started_at) * 1000, 2),
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        await _record_failure(
            request=request,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_category="payload_validation_failed",
            error_detail=json.dumps(exc.errors(), ensure_ascii=True),
        )
        return _json_error(
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payload validation failed.",
            error_category="payload_validation_failed",
            extra={"errors": exc.errors()},
        )

    @app.exception_handler(StorageError)
    async def storage_exception_handler(request: Request, exc: StorageError) -> RawResponse:
        await _record_failure(
            request=request,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_category=exc.error_category,
            error_detail=str(exc),
        )
        # für Dashboard-Routen: HTML-Fehlerseite
        if "/dashboard" in str(request.url.path):
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "status_code": 503, "detail": exc.public_message},
                status_code=503,
            )
        # für API-Aufrufe: JSON-Fehler
        return _json_error(
            request=request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.public_message,
            error_category=exc.error_category,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> RawResponse:
        if request.url.path == "/live-location" and exc.status_code in {401, 429}:
            await _record_failure(
                request=request,
                http_status=exc.status_code,
                error_category="authentication_failed" if exc.status_code == 401 else "rate_limited",
                error_detail=str(exc.detail),
            )
        # für Dashboard-Routen: HTML-Fehlerseite
        accept = request.headers.get("accept", "")
        if "/dashboard" in str(request.url.path) or "text/html" in accept:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "status_code": exc.status_code, "detail": exc.detail},
                status_code=exc.status_code,
            )
        # für API-Aufrufe: JSON-Fehler
        payload: dict[str, Any] = {
            "status": "error",
            "requestId": request.state.request_id,
            "error": {"category": "http_error", "detail": exc.detail},
        }
        response = JSONResponse(status_code=exc.status_code, content=payload)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> RawResponse:
        await _record_failure(
            request=request,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_category="unexpected_internal_error",
            error_detail=repr(exc),
        )
        # für Dashboard-Routen: HTML-Fehlerseite
        accept = request.headers.get("accept", "")
        if "/dashboard" in str(request.url.path) or "text/html" in accept:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "status_code": 500, "detail": "Unexpected internal server error."},
                status_code=500,
            )
        # für API-Aufrufe: JSON-Fehler
        return _json_error(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected internal server error.",
            error_category="unexpected_internal_error",
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        readiness = _storage(request).readiness()
        return {
            "status": "ok",
            "service": "lh2gpx-live-receiver",
            "time": datetime.now(timezone.utc).isoformat(),
            "requestId": request.state.request_id,
            "authRequired": _settings(request).auth_required,
            "storageReady": readiness.is_ready,
            "storageWritable": readiness.writable,
            "storageMessage": readiness.message,
            "sqlitePath": readiness.sqlite_path,
            "rawPayloadNdjsonPath": readiness.raw_ndjson_path,
        }

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        readiness = _storage(request).readiness()
        status_code = status.HTTP_200_OK if readiness.is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if readiness.is_ready else "not_ready",
                "requestId": request.state.request_id,
                "storageWritable": readiness.writable,
                "message": readiness.message,
                "sqlitePath": readiness.sqlite_path,
            },
        )

    @app.post(
        "/live-location",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(_require_bearer_token), Depends(_apply_rate_limit)],
    )
    async def receive_live_location(payload: LiveLocationRequest, request: Request, response: Response) -> dict[str, Any]:
        metadata = _request_metadata(request)
        raw_payload_text = request.state.raw_body_text or json.dumps(payload.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
        storage_summary = _storage(request).ingest_success(
            payload=payload,
            metadata=metadata,
            raw_payload_text=raw_payload_text,
        )
        request.state.log_fields = {
            "session_id": str(payload.sessionID),
            "capture_mode": payload.captureMode,
            "source": payload.source,
            "points_count": len(payload.points),
            "first_point_ts": payload.points[0].timestamp.astimezone(timezone.utc).isoformat(),
            "last_point_ts": payload.points[-1].timestamp.astimezone(timezone.utc).isoformat(),
            "storage_target": str(_storage(request).sqlite_path),
        }
        response.headers["Cache-Control"] = "no-store"
        # Phase 4: Echtzeit-Push via WebSocket
        await manager.broadcast({"type": "new_location", "sessionId": str(payload.sessionID)})
        return {"status": "accepted", "requestId": metadata.request_id, **storage_summary}

    @app.websocket("/ws/map")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                # Wir warten nur auf das Schließen der Verbindung
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    @app.get("/api/stats", dependencies=[Depends(_require_admin_access)])
    async def api_stats(request: Request) -> dict[str, Any]:
        return {"requestId": request.state.request_id, "stats": _storage(request).get_stats()}

    @app.get("/api/live-summary", dependencies=[Depends(_require_admin_access)])
    async def api_live_summary(
        request: Request,
        limit: int = Query(default=100, ge=1, le=10000),
    ) -> dict[str, Any]:
        summary = _storage(request).get_live_summary(limit=limit)
        return {"requestId": request.state.request_id, **summary}

    @app.get("/api/config-summary", dependencies=[Depends(_require_admin_access)])
    async def api_config_summary(request: Request) -> dict[str, Any]:
        return {
            "requestId": request.state.request_id,
            "config": _settings(request).masked_config_summary(),
            "readiness": asdict(_storage(request).readiness()),
            "explanations": _config_explanations(),
        }

    @app.post("/api/settings", dependencies=[Depends(_require_admin_access)])
    async def api_save_settings(request: Request) -> dict[str, Any]:
        try:
            updates = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        try:
            # Persistenz speichern mit Validierung
            _settings(request).save_persistent(updates)
            
            # Hot-Reload: Neue Settings laden
            new_settings = Settings.from_env()
            request.app.state.settings = new_settings
            
            # Logging-Level live anpassen
            _configure_logging(new_settings.log_level)
            
            # Storage neu initialisieren (Hot-Swap)
            new_storage = ReceiverStorage(new_settings)
            new_storage.startup()
            request.app.state.storage = new_storage
            request.app.state.rate_limiter = SimpleRateLimiter(new_settings.rate_limit_requests_per_minute)
            request.app.state.session_signing_key = _build_session_signing_key(
                new_settings,
                existing_key=getattr(request.app.state, "session_signing_key", None),
            )
            
            # Templates-Globals aktualisieren
            templates.env.globals.update(
                format_timestamp=lambda value: _timestamp_summary(value, new_settings.local_timezone),
            )
            
            LOGGER.info(f"Settings updated live: {list(updates.keys())}")
            
            return {
                "status": "success",
                "message": "Settings saved and applied live.",
                "requestId": request.state.request_id,
                "config": new_settings.masked_config_summary()
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            LOGGER.error(f"Failed to apply settings: {exc}")
            raise HTTPException(status_code=500, detail="Internal server error during hot-reload")

    @app.get("/api/points", dependencies=[Depends(_require_admin_access)])
    async def api_points(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        search: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1),
        format: str = Query(default="json"),
    ):
        if format not in {"json", "csv", "ndjson", "geojson"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported export format.")
        effective_page_size = min(page_size or _settings(request).points_page_size_default, _settings(request).points_page_size_max)
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            search=search,
            page=page,
            page_size=effective_page_size,
        )
        if format != "json":
            payload, media_type = _storage(request).export_points(filters, export_format=format)
            extension = "json" if format == "json" else format
            return RawResponse(
                content=payload,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="gps-points.{extension}"'},
            )

        # Cache-Key = normalisierter Query-String (ohne requestId)
        cache_key = str(request.url.query)
        now = time.time()
        cached = _POINTS_CACHE.get(cache_key)

        if cached and (now - cached[0]) < _POINTS_CACHE_TTL:
            _, etag, body = cached
        else:
            result = {"requestId": request.state.request_id, "points": _storage(request).list_points(filters)}
            body = json.dumps(result, separators=(",", ":")).encode()
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            _POINTS_CACHE[cache_key] = (now, etag, body)
            # Cache begrenzen: bei >200 Einträgen alle abgelaufenen entfernen
            if len(_POINTS_CACHE) > 200:
                cutoff = now - _POINTS_CACHE_TTL
                for k in [k for k, v in _POINTS_CACHE.items() if v[0] < cutoff]:
                    del _POINTS_CACHE[k]

        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"})

        return Response(
            content=body,
            media_type="application/json",
            headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"},
        )

    @app.get("/api/timeline", dependencies=[Depends(_require_admin_access)])
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
        viewport_bbox = _parse_bbox(bbox)
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
        cached = _cache_get(_POINTS_CACHE, cache_key, ttl=_POINTS_CACHE_TTL)
        if cached:
            _, etag, body = cached
        else:
            now = time.time()
            raw_items = _storage(request).list_timeline_points(filters, bbox=viewport_bbox, limit=50000)
            items = _adaptive_timeline_sample(raw_items, limit=limit)
            markers = _build_timeline_markers(
                raw_items,
                stop_min_duration_min=stop_min_duration_min,
                stop_radius_m=stop_radius_m,
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
            _cache_put(_POINTS_CACHE, cache_key, (now, etag, body), ttl=_POINTS_CACHE_TTL, max_items=_POINTS_CACHE_MAX)
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304, headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"})
        return Response(content=body, media_type="application/json", headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"})

    @app.get("/api/timeline-preview", dependencies=[Depends(_require_admin_access)])
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
        configured_max = max(1, _settings(request).points_page_size_max)
        effective_page_size = min(page_size or configured_max, configured_max, _MAP_DATA_PAGE_SIZE_MAX)
        effective_log_limit = min(log_limit or effective_page_size, effective_page_size)
        effective_zoom = max(1, min(22, round(zoom)))
        viewport_bbox = _parse_bbox(bbox)
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            page=1,
            page_size=effective_page_size,
        )
        cache_key = f"timeline-preview:{request.url.query}"
        cached = _cache_get(_TIMELINE_PREVIEW_CACHE, cache_key, ttl=_TIMELINE_PREVIEW_CACHE_TTL)
        cache_state = "miss"
        counts_duration_ms = 0.0
        preview_duration_ms = 0.0
        serialize_duration_ms = 0.0
        if cached:
            _, etag, body = cached
            cache_state = "hit"
        else:
            now = time.time()
            storage = _storage(request)
            counts_started_at = time.perf_counter()
            if viewport_bbox:
                viewport_items = storage.list_points_in_bbox(filters, bbox=viewport_bbox)
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
                _prepare_timeline_preview_payload,
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
            result = {"requestId": request.state.request_id, **payload, "processing": _summarize_import_tasks()}
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            _cache_put(
                _TIMELINE_PREVIEW_CACHE,
                cache_key,
                (now, etag, body),
                ttl=_TIMELINE_PREVIEW_CACHE_TTL,
                max_items=_BODY_CACHE_MAX,
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

    @app.get("/api/map-meta", dependencies=[Depends(_require_admin_access)])
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
        cached = _cache_get(_MAP_META_CACHE, cache_key, ttl=_MAP_META_CACHE_TTL)
        cache_state = "miss"
        summary_duration_ms = 0.0
        serialize_duration_ms = 0.0
        if cached:
            _, etag, body = cached
            cache_state = "hit"
        else:
            summary_started_at = time.perf_counter()
            summary = _storage(request).summarize_points(filters)
            summary_duration_ms = round((time.perf_counter() - summary_started_at) * 1000, 2)
            result = {
                "requestId": request.state.request_id,
                "meta": summary,
                "processing": _summarize_import_tasks(),
            }
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            _cache_put(_MAP_META_CACHE, cache_key, (now, etag, body), ttl=_MAP_META_CACHE_TTL, max_items=_BODY_CACHE_MAX)
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

    @app.get("/api/map-data", dependencies=[Depends(_require_admin_access)])
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
        configured_max = max(1, _settings(request).points_page_size_max)
        viewport_bbox = _parse_bbox(bbox)
        effective_page_size = min(
            page_size or configured_max,
            configured_max,
            _MAP_DATA_PAGE_SIZE_MAX,
        )
        effective_log_limit = min(log_limit or effective_page_size, effective_page_size)
        effective_zoom = max(1, min(22, round(zoom)))
        padded_bbox = _expand_bbox(viewport_bbox, zoom=effective_zoom) if viewport_bbox else None
        filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            page=1,
            page_size=effective_page_size,
        )

        cache_key = str(request.url.query)
        now = time.time()
        cached = _cache_get(_MAP_DATA_CACHE, cache_key, ttl=_MAP_DATA_CACHE_TTL)
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
        else:
            storage = _storage(request)
            if latest_known_ts:
                latest_check_started_at = time.perf_counter()
                latest_visible_ts = storage.latest_point_timestamp(filters, bbox=viewport_bbox)
                latest_visible_dt = _parse_iso_timestamp(latest_visible_ts)
                latest_known_dt = _parse_iso_timestamp(latest_known_ts)
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
                            "Server-Timing": ", ".join(
                                [
                                    'cache;desc="miss"',
                                    f"latest_check;dur={latest_check_duration_ms:.2f}",
                                    f"total;dur={total_duration_ms:.2f}",
                                ]
                            ),
                        },
                    )
            if viewport_bbox:
                counts_started_at = time.perf_counter()
                total_points = storage.count_points(filters)
                viewport_items = storage.list_points_in_bbox(filters, bbox=viewport_bbox)
                visible_points = len(viewport_items)
                counts_duration_ms = round((time.perf_counter() - counts_started_at) * 1000, 2)
            else:
                counts_started_at = time.perf_counter()
                listed = storage.list_points(filters)
                total_points = listed["total"]
                visible_points = len(listed["items"])
                viewport_items = listed["items"]
                counts_duration_ms = round((time.perf_counter() - counts_started_at) * 1000, 2)
            buffered_items = viewport_items
            delta_viewport_items = []
            delta_polyline_entries: list[dict[str, Any]] = []
            delta_speed_entries: list[dict[str, Any]] = []
            delta_stop_entries: list[dict[str, Any]] = []
            delta_daytrack_entries: list[dict[str, Any]] = []
            delta_snap_entries: list[dict[str, Any]] = []
            delta_mode = False
            latest_visible_ts = viewport_items[0]["point_timestamp_utc"] if viewport_items else None
            if latest_known_ts:
                latest_known_dt = _parse_iso_timestamp(latest_known_ts)
                if latest_known_dt:
                    delta_mode = True
                    map_mode = "delta"
                    normalized_since = latest_known_dt.astimezone(timezone.utc).isoformat()
                    delta_viewport_items = storage.list_points_since(filters, since_utc=normalized_since, bbox=viewport_bbox)
            heatmap_entries = []
            if include_heatmap:
                heatmap_started_at = time.perf_counter()
                heatmap_entries = _aggregate_heatmap(viewport_items, zoom=effective_zoom)
                heatmap_duration_ms = round((time.perf_counter() - heatmap_started_at) * 1000, 2)
            track_layers = {
                "polylines": [],
                "speed": [],
                "stops": [],
                "daytracks": [],
                "snap": [],
                "context_points_desc": viewport_items,
                "segment_count": 0,
            }
            needs_track_context = include_polyline or include_labels or include_speed or include_stops or include_daytrack or include_snap
            defer_expensive_track_layers = delta_mode and len(delta_viewport_items) <= 24
            if needs_track_context:
                preloaded_track_points = None
                if not viewport_bbox or padded_bbox == viewport_bbox:
                    preloaded_track_points = viewport_items
                track_context_started_at = time.perf_counter()
                track_context = await asyncio.to_thread(
                    _resolve_track_context,
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
                    _resolve_track_layers,
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
                track_layers_duration_ms = round((time.perf_counter() - track_layers_started_at) * 1000, 2)
                buffered_items = track_layers["context_points_desc"]
                if delta_mode and delta_viewport_items:
                    delta_context_points_asc = _build_delta_context_points_asc(viewport_items, delta_viewport_items)
                    if delta_context_points_asc:
                        delta_segments = _segment_track(
                            delta_context_points_asc,
                            time_gap_ms=route_time_gap_min * 60000,
                            dist_gap_m=route_dist_gap_m,
                        )
                        if include_polyline or include_labels:
                            delta_polyline_entries = _serialize_polyline_segments(
                                delta_segments,
                                zoom=effective_zoom,
                                include_labels=include_labels,
                            )
                        if include_speed and not defer_expensive_track_layers:
                            delta_speed_entries = _serialize_speed_segments(delta_context_points_asc, zoom=effective_zoom)
                        if include_stops and not defer_expensive_track_layers:
                            delta_stop_entries = _detect_stops(
                                delta_context_points_asc,
                                stop_radius_m=stop_radius_m,
                                stop_min_duration_min=stop_min_duration_min,
                            )
                        if include_daytrack and not defer_expensive_track_layers:
                            delta_daytrack_entries = _serialize_daytracks(
                                delta_context_points_asc,
                                zoom=effective_zoom,
                                route_time_gap_min=route_time_gap_min,
                            )
                        if include_snap and len(delta_segments) <= 2 and len(delta_viewport_items) <= 8:
                            delta_snap_entries = _serialize_snap_segments(delta_segments, zoom=effective_zoom)
            if delta_mode:
                payload_started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    _prepare_map_delta_payload,
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
                    include_speed=include_speed and not defer_expensive_track_layers,
                    include_stops=include_stops and not defer_expensive_track_layers,
                    include_daytrack=include_daytrack and not defer_expensive_track_layers,
                    include_snap=include_snap and not delta_mode,
                )
                payload_duration_ms = round((time.perf_counter() - payload_started_at) * 1000, 2)
            else:
                payload_started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    _prepare_map_payload,
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
            result["processing"] = _summarize_import_tasks()
            serialize_started_at = time.perf_counter()
            body = json.dumps(result, separators=(",", ":")).encode()
            serialize_duration_ms = round((time.perf_counter() - serialize_started_at) * 1000, 2)
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            _cache_put(_MAP_DATA_CACHE, cache_key, (now, etag, body), ttl=_MAP_DATA_CACHE_TTL, max_items=_BODY_CACHE_MAX)
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

    @app.get("/api/points/{point_id}", dependencies=[Depends(_require_admin_access)])
    async def api_point_detail(request: Request, point_id: int) -> dict[str, Any]:
        item = _storage(request).get_point(point_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Point not found.")
        return {"requestId": request.state.request_id, "point": item}

    @app.get("/api/requests", dependencies=[Depends(_require_admin_access)])
    async def api_requests(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        ingest_status: str | None = Query(default=None),
        search: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        effective_page_size = min(page_size or _settings(request).points_page_size_default, _settings(request).points_page_size_max)
        filters = RequestFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            ingest_status=ingest_status,
            search=search,
            page=page,
            page_size=effective_page_size,
        )
        return {"requestId": request.state.request_id, "requests": _storage(request).list_requests(filters)}

    @app.get("/api/requests/{request_id}", dependencies=[Depends(_require_admin_access)])
    async def api_request_detail(request: Request, request_id: str) -> dict[str, Any]:
        item = _storage(request).get_request(request_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
        return {"requestId": request.state.request_id, "request": item}

    @app.get("/api/sessions", dependencies=[Depends(_require_admin_access)])
    async def api_sessions(request: Request) -> dict[str, Any]:
        return {"requestId": request.state.request_id, "sessions": _storage(request).list_sessions()}

    @app.get("/api/sessions/{session_id}", dependencies=[Depends(_require_admin_access)])
    async def api_session_detail(request: Request, session_id: str) -> dict[str, Any]:
        item = _storage(request).get_session(session_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        return {"requestId": request.state.request_id, "session": item}

    @app.exception_handler(_LoginRequired)
    async def login_required_handler(request: Request, exc: _LoginRequired) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request, error: str | None = None) -> HTMLResponse:
        settings = _settings(request)
        server_url = settings.public_base_url.rstrip("/") + "/live-location"
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"server_url": server_url, "error": error},
        )

    @app.post("/login", include_in_schema=False, response_model=None)
    async def login_submit(request: Request) -> RedirectResponse | HTMLResponse:
        settings = _settings(request)
        raw_body = await request.body()
        form = {k: v[0] for k, v in parse_qs(raw_body.decode("utf-8", errors="replace")).items()}
        supplied_url = form.get("server_url", "").strip()
        supplied_token = form.get("bearer_token", "").strip()

        expected_url = settings.public_base_url.rstrip("/") + "/live-location"
        url_ok = not supplied_url or supplied_url.rstrip("/") == expected_url.rstrip("/")
        token_ok = settings.bearer_token and compare_digest(supplied_token, settings.bearer_token)

        if not url_ok or not token_ok:
            server_url = expected_url
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"server_url": server_url, "error": "Ungültige Anmeldedaten."},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        token = _create_session_token(settings, request.app)
        redirect = RedirectResponse(url="/dashboard/map", status_code=status.HTTP_303_SEE_OTHER)
        redirect.set_cookie(
            key=_SESSION_COOKIE,
            value=token,
            max_age=_SESSION_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=True,
        )
        return redirect

    @app.get("/logout", include_in_schema=False)
    async def logout(request: Request) -> RedirectResponse:
        redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        redirect.delete_cookie(key=_SESSION_COOKIE, samesite="strict")
        return redirect

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home(request: Request) -> HTMLResponse:
        endpoint_count = len([r for r in app.routes if hasattr(r, 'path')])
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={
                "app_version": request.app.version,
                "endpoint_count": endpoint_count,
            },
        )

    @app.get("/admin", include_in_schema=False)
    async def admin_redirect() -> RedirectResponse:
        return RedirectResponse(url="/dashboard/map", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        search: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1),
    ) -> HTMLResponse:
        effective_page_size = min(page_size or _settings(request).points_page_size_default, _settings(request).points_page_size_max)
        point_filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            search=search,
            page=page,
            page_size=effective_page_size,
        )
        snapshot = _dashboard_snapshot(request)
        try:
            recent_points = _storage(request).list_points(PointFilters(page=1, page_size=8))
        except StorageError:
            recent_points = {"items": [], "page": 1, "pageSize": 8, "total": 0}
        context = _base_template_context(
            request,
            active_nav="dashboard",
            page_title="Receiver-Dashboard",
            page_kicker="Receiver-first operator view",
            page_description="Der aktuelle Betriebszustand, die letzten Ingests und die wichtigsten Arbeitsbereiche fuer den Serverbetrieb auf einen Blick.",
            snapshot=snapshot,
        )
        context.update(
            {
                "filters": point_filters,
                "recent_points": recent_points["items"],
                "recent_requests": snapshot["lists"]["recentRequests"][:6],
                "recent_sessions": snapshot["lists"]["recentSessions"][:6],
                "top_sessions": snapshot["lists"]["topSessions"],
                "point_filter_exports": _point_export_links(point_filters),
                "config_summary": _settings(request).masked_config_summary(),
                "config_explanations": _config_explanations(),
            }
        )
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context)

    @app.get("/dashboard/map", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_map(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        try:
            all_sessions = _storage(request).list_sessions()
        except StorageError:
            all_sessions = []
        sessions = [s for s in all_sessions if not (s.get("source") or "").startswith("import:")]
        import_sessions = [s for s in all_sessions if (s.get("source") or "").startswith("import:")]

        context = _base_template_context(
            request,
            active_nav="map",
            page_title="Interaktive Karte",
            page_kicker="Standort-Visualisierung",
            page_description="Visualisierung der empfangenen GPS-Punkte auf einer interaktiven Karte mit flexiblen Zeitfiltern.",
            snapshot=snapshot,
        )
        context.update({
            "sessions": sessions,
            "import_sessions": import_sessions,
            "config_summary": _settings(request).masked_config_summary(),
        })
        return templates.TemplateResponse(request=request, name="map.html", context=context)

    @app.get("/dashboard/import", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_import(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        try:
            all_sessions = _storage(request).list_sessions()
        except StorageError:
            all_sessions = []
        import_sessions = [s for s in all_sessions if (s.get("source") or "").startswith("import:")]
        context = _base_template_context(
            request, active_nav="import",
            page_title="Import", page_kicker="GPS-Daten importieren",
            page_description="Importiere GPS-Daten aus Google Maps, GPX, KML, KMZ, GeoJSON, CSV oder ZIP.",
            snapshot=snapshot,
        )
        context["import_sessions"] = import_sessions
        return templates.TemplateResponse(request=request, name="import.html", context=context)

    @app.delete("/api/sessions/{session_id}", dependencies=[Depends(_require_admin_access)])
    async def api_delete_session(request: Request, session_id: str) -> JSONResponse:
        try:
            deleted = _storage(request).delete_session(session_id)
        except StorageError as e:
            raise HTTPException(status_code=503, detail=str(e))
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Session nicht gefunden oder bereits leer.")
        return JSONResponse({"ok": True, "deleted": deleted, "session_id": session_id})

    @app.post("/api/import", dependencies=[Depends(_require_admin_access)])
    async def api_import(request: Request, file: UploadFile = File(...)) -> JSONResponse:
        MAX_BYTES = 100 * 1024 * 1024  # 100 MB
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Datei zu groß (max. 100 MB).")
        filename = file.filename or "upload"
        task_id = str(uuid4())
        _import_tasks[task_id] = {
            "status": "queued",
            "filename": filename,
            "file_size_bytes": len(data),
            "created_at": isoformat_utc(datetime.now(timezone.utc)),
            "updated_at": isoformat_utc(datetime.now(timezone.utc)),
            "metrics": {},
            "warnings": [],
        }
        if request.app.state.inline_import_tasks:
            await _run_import_task(task_id, filename, data, _storage(request))
        else:
            asyncio.create_task(_run_import_task(task_id, filename, data, _storage(request)))
        return JSONResponse({"ok": True, "task_id": task_id, "filename": filename, "file_size_bytes": len(data)})

    @app.get("/api/import/status/{task_id}", dependencies=[Depends(_require_admin_access)])
    async def api_import_status(task_id: str) -> JSONResponse:
        task = _import_tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task nicht gefunden oder abgelaufen.")
        return JSONResponse(task)

    @app.post("/api/storage/vacuum", dependencies=[Depends(_require_admin_access)])
    async def api_storage_vacuum(request: Request) -> JSONResponse:
        try:
            result = await asyncio.to_thread(_storage(request).vacuum)
        except StorageError as e:
            raise HTTPException(status_code=503, detail=str(e))
        return JSONResponse({"ok": True, **result})

    @app.get("/dashboard/live-status", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_live_status(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="live_status",
            page_title="Live-Status",
            page_kicker="Health, readiness und Ingest-Zustand",
            page_description="Hier ist konzentriert sichtbar, ob der Receiver sauber laeuft, ob Storage schreibbereit ist und welche Fehler zuletzt aufgetreten sind.",
            snapshot=snapshot,
        )
        return templates.TemplateResponse(request=request, name="live_status.html", context=context)

    @app.get("/dashboard/activity", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_activity(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="activity",
            page_title="Letzte Aktivitaet",
            page_kicker="Requests, Sessions und Punkte",
            page_description="Zeitfenster, Trends und die juengsten Datenbewegungen des Receivers fuer die Operator-Sicht.",
            snapshot=snapshot,
        )
        return templates.TemplateResponse(request=request, name="activity.html", context=context)

    @app.get("/dashboard/points", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_points(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        search: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1),
    ) -> HTMLResponse:
        effective_page_size = min(page_size or _settings(request).points_page_size_default, _settings(request).points_page_size_max)
        point_filters = PointFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            search=search,
            page=page,
            page_size=effective_page_size,
        )
        try:
            points = _storage(request).list_points(point_filters)
        except StorageError:
            points = {"page": page, "pageSize": effective_page_size, "total": 0, "items": []}
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="points",
            page_title="Punkte",
            page_kicker="Detailansicht der gespeicherten GPS-Punkte",
            page_description="Filterbare Punkteliste mit UTC- und Lokalzeit, Exporten und Direktsprung zu Session und Request.",
            snapshot=snapshot,
        )
        context.update({"filters": point_filters, "points": points, "point_filter_exports": _point_export_links(point_filters)})
        return templates.TemplateResponse(request=request, name="points.html", context=context)

    @app.get("/dashboard/points/{point_id}", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_point_detail(request: Request, point_id: int) -> HTMLResponse:
        item = _storage(request).get_point(point_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Point not found.")
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="points",
            page_title=f"Punkt #{point_id}",
            page_kicker="Punktdetail",
            page_description="Zeit, Genauigkeit und Referenzen dieses gespeicherten GPS-Punkts.",
            snapshot=snapshot,
        )
        context.update({"point_item": item})
        return templates.TemplateResponse(request=request, name="point_detail.html", context=context)

    @app.get("/dashboard/requests", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_requests(
        request: Request,
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        time_from: str | None = Query(default=None),
        time_to: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        capture_mode: str | None = Query(default=None),
        source: str | None = Query(default=None),
        ingest_status: str | None = Query(default=None),
        search: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1),
    ) -> HTMLResponse:
        effective_page_size = min(page_size or _settings(request).points_page_size_default, _settings(request).points_page_size_max)
        request_filters = RequestFilters(
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            session_id=session_id,
            capture_mode=capture_mode,
            source=source,
            ingest_status=ingest_status,
            search=search,
            page=page,
            page_size=effective_page_size,
        )
        try:
            requests_payload = _storage(request).list_requests(request_filters)
        except StorageError:
            requests_payload = {"page": page, "pageSize": effective_page_size, "total": 0, "items": []}
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="requests",
            page_title="Requests",
            page_kicker="Ingest-Historie",
            page_description="Alle empfangenen Requests mit Status, Antwortcode, Fehlerkategorie und Sprung in die Detailansicht.",
            snapshot=snapshot,
        )
        context.update({"filters": request_filters, "requests_payload": requests_payload})
        return templates.TemplateResponse(request=request, name="requests.html", context=context)

    @app.get("/dashboard/requests/{request_id}", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_request_detail(request: Request, request_id: str) -> HTMLResponse:
        item = _storage(request).get_request(request_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="requests",
            page_title=f"Request {request_id}",
            page_kicker="Requestdetail",
            page_description="Detailansicht eines einzelnen Ingest-Requests mit Rohpayload, Punkten und Fehlerkontext.",
            snapshot=snapshot,
        )
        context.update({"request_item": item})
        return templates.TemplateResponse(request=request, name="request_detail.html", context=context)

    @app.get("/dashboard/sessions", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_sessions(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        try:
            sessions = _storage(request).list_sessions()
        except StorageError:
            sessions = []
        context = _base_template_context(
            request,
            active_nav="sessions",
            page_title="Sessions",
            page_kicker="Session-Uebersicht",
            page_description="Aktive und historische Sessions mit Punktanzahl, Requestvolumen, Zeitspanne und Sprung in die Sessiondetails.",
            snapshot=snapshot,
        )
        context.update({"sessions": sessions})
        return templates.TemplateResponse(request=request, name="sessions.html", context=context)

    @app.get("/dashboard/sessions/{session_id}", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_session_detail(request: Request, session_id: str) -> HTMLResponse:
        item = _storage(request).get_session(session_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="sessions",
            page_title=f"Session {session_id}",
            page_kicker="Sessiondetail",
            page_description="Alle Punkte und Requests einer Session inklusive Bounding Box, Zeitspanne und Genauigkeitsbild.",
            snapshot=snapshot,
        )
        context.update({"session_item": item})
        return templates.TemplateResponse(request=request, name="session_detail.html", context=context)

    @app.get("/dashboard/exports", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_exports(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="exports",
            page_title="Exporte",
            page_kicker="Datenabzug und API-Schnittstellen",
            page_description="Verfuegbare Exportformate fuer Punkte sowie die passenden Arbeitswege fuer Operatoren im Tagesbetrieb.",
            snapshot=snapshot,
        )
        return templates.TemplateResponse(request=request, name="exports.html", context=context)

    @app.get("/dashboard/config", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_config(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="config",
            page_title="Konfiguration",
            page_kicker="Maskierte Runtime-Konfiguration",
            page_description="Host, Ports, Limits, Auth-Schalter und Speicherpfade werden operator-sicher und ohne Klartext-Secrets dargestellt.",
            snapshot=snapshot,
        )
        context.update(
            {
                "config_summary": _settings(request).masked_config_summary(),
                "config_explanations": _config_explanations(),
            }
        )
        return templates.TemplateResponse(request=request, name="config.html", context=context)

    @app.get("/dashboard/storage", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_storage(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="storage",
            page_title="Storage",
            page_kicker="SQLite, Audit-Datei und Schreibbereitschaft",
            page_description="Speicherort, Dateigroessen, letzte Schreibzeiten und Storage-Befund fuer den laufenden Receiver.",
            snapshot=snapshot,
        )
        return templates.TemplateResponse(request=request, name="storage.html", context=context)

    @app.get("/dashboard/security", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_security(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="security",
            page_title="Sicherheit",
            page_kicker="Auth-Status und Security-Hinweise",
            page_description="Welche Schutzmechanismen aktiv sind, welche Werte maskiert bleiben und welche Folgearbeiten laut Doku noch offen sind.",
            snapshot=snapshot,
        )
        context.update(
            {
                "doc_sections": _load_markdown_outline(DOCS_DIR / "SECURITY.md"),
                "open_items": _load_markdown_outline(DOCS_DIR / "OPEN_ITEMS.md"),
                "config_summary": _settings(request).masked_config_summary(),
            }
        )
        return templates.TemplateResponse(request=request, name="security.html", context=context)

    @app.get("/dashboard/system", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_system(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="system",
            page_title="System",
            page_kicker="Version, Laufzeit und Changelog",
            page_description="App-Version, Python-Laufzeit, Startzeit und die wichtigsten zuletzt dokumentierten Receiver-Aenderungen.",
            snapshot=snapshot,
        )
        context.update(
            {
                "changelog_sections": _load_markdown_outline(ROOT_DIR / "CHANGELOG.md"),
                "runtime_info": {
                    "appVersion": request.app.version,
                    "pythonVersion": platform.python_version(),
                    "currentUtc": datetime.now(timezone.utc).isoformat(),
                    "startedAtUtc": request.app.state.started_at_utc.isoformat(),
                    "uptime": _format_duration(int((datetime.now(timezone.utc) - request.app.state.started_at_utc).total_seconds())),
                },
            }
        )
        return templates.TemplateResponse(request=request, name="system.html", context=context)

    @app.get("/dashboard/troubleshooting", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_troubleshooting(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="troubleshooting",
            page_title="Troubleshooting",
            page_kicker="Bekannte Fehlerbilder und direkte Hilfen",
            page_description="Die zentralen Diagnosepfade aus der Receiver-Dokumentation direkt in der Admin-Oberflaeche.",
            snapshot=snapshot,
        )
        context.update({"doc_sections": _load_markdown_outline(DOCS_DIR / "TROUBLESHOOTING.md")})
        return templates.TemplateResponse(request=request, name="doc_page.html", context=context)

    @app.get("/dashboard/open-items", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_open_items(request: Request) -> HTMLResponse:
        snapshot = _dashboard_snapshot(request)
        context = _base_template_context(
            request,
            active_nav="open_items",
            page_title="Open Items",
            page_kicker="Bewusst offene Receiver-Punkte",
            page_description="Was fuer den aktuellen Scope fertig ist und welche Folgearbeiten bewusst getrennt bleiben.",
            snapshot=snapshot,
        )
        context.update({"doc_sections": _load_markdown_outline(DOCS_DIR / "OPEN_ITEMS.md")})
        return templates.TemplateResponse(request=request, name="doc_page.html", context=context)

    return app


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", force=True)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _storage(request: Request) -> ReceiverStorage:
    return request.app.state.storage


def _parse_bbox(raw_bbox: str | None) -> tuple[float, float, float, float] | None:
    if not raw_bbox:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = [float(part.strip()) for part in raw_bbox.split(",")]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bbox: {raw_bbox}") from exc
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180 and -90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise HTTPException(status_code=400, detail="Invalid bbox coordinates")
    if min_lat > max_lat:
        raise HTTPException(status_code=400, detail="Invalid bbox latitude ordering")
    return (min_lon, min_lat, max_lon, max_lat)


def _expand_bbox(bbox: tuple[float, float, float, float], *, zoom: int) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_span = max(0.001, (max_lon - min_lon) % 360 if min_lon > max_lon else max_lon - min_lon)
    lat_span = max(0.001, max_lat - min_lat)
    factor = 0.35 if zoom <= 8 else 0.22 if zoom <= 11 else 0.12 if zoom <= 14 else 0.06
    lon_pad = min(10.0, max(0.002, lon_span * factor))
    lat_pad = min(10.0, max(0.002, lat_span * factor))
    expanded_min_lon = min_lon - lon_pad
    expanded_max_lon = max_lon + lon_pad
    while expanded_min_lon < -180:
        expanded_min_lon += 360
    while expanded_max_lon > 180:
        expanded_max_lon -= 360
    return (
        expanded_min_lon,
        max(-90.0, min_lat - lat_pad),
        expanded_max_lon,
        min(90.0, max_lat + lat_pad),
    )


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
) -> dict[str, Any]:
    if not buffered_points_desc:
        return {
            "meta": {"totalPoints": total_points, "visiblePoints": visible_points, "loadedPoints": 0, "serverPrepared": True},
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
            payload["delta"]["appendStops"] = delta_stop_entries
        else:
            payload["delta"]["replaceStops"] = stop_entries
    if include_daytrack:
        if delta_daytrack_entries:
            payload["delta"]["appendDaytracks"] = delta_daytrack_entries
        else:
            payload["delta"]["replaceDaytracks"] = daytrack_entries
    if include_snap:
        if delta_snap_entries:
            payload["delta"]["appendSnap"] = delta_snap_entries
        else:
            payload["delta"]["replaceSnap"] = snap_entries
    return payload


def _build_delta_context_points_asc(
    current_viewport_points_desc: list[dict[str, Any]],
    new_viewport_points_desc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not new_viewport_points_desc:
        return []
    old_anchor = None
    if len(current_viewport_points_desc) > len(new_viewport_points_desc):
        old_anchor = current_viewport_points_desc[len(new_viewport_points_desc)]
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
            "polylines": _serialize_polyline_segments(segments, zoom=zoom, include_labels=include_labels)
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


def _serialize_polyline_segments(
    segments: list[list[dict[str, Any]]],
    *,
    zoom: int,
    include_labels: bool,
) -> list[dict[str, Any]]:
    serialized = []
    for index, segment in enumerate(segments):
        coords = _snap_segment(segment, zoom=zoom) or _simplify_segment(segment, zoom)
        serialized.append(
            {
                "color": _palette_color(index),
                "coords": coords,
                "pointsCount": len(segment),
                "startLabel": (segment[0]["point_timestamp_local"] or "")[11:16] if include_labels else "",
                "endLabel": (segment[-1]["point_timestamp_local"] or "")[11:16] if include_labels else "",
                "startPoint": coords[0] if coords else [float(segment[0]["latitude"]), float(segment[0]["longitude"])],
                "endPoint": coords[-1] if coords else [float(segment[-1]["latitude"]), float(segment[-1]["longitude"])],
            }
        )
    return serialized


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
    lat_step = max((_heat_cell_m(zoom) / 111320.0) * 0.5, 1e-5)
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        _bucket_float(min_lon, step=lat_step),
        _bucket_float(min_lat, step=lat_step),
        _bucket_float(max_lon, step=lat_step),
        _bucket_float(max_lat, step=lat_step),
    )


def _resolve_heatmap_layer(
    storage: ReceiverStorage,
    filters: PointFilters,
    *,
    bbox: tuple[float, float, float, float] | None,
    zoom: int,
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
    cached = _cache_get(_HEATMAP_LAYER_CACHE, cache_key, ttl=_HEATMAP_LAYER_CACHE_TTL)
    if cached:
        return cached[1]

    now = time.time()
    rows = storage.list_heatmap_points(filters, bbox=bbox)
    result = _aggregate_heatmap(rows, zoom=zoom)
    _cache_put(_HEATMAP_LAYER_CACHE, cache_key, (now, result), ttl=_HEATMAP_LAYER_CACHE_TTL, max_items=_LAYER_CACHE_MAX)
    return result


def _resolve_track_context(
    storage: ReceiverStorage,
    filters: PointFilters,
    *,
    bbox: tuple[float, float, float, float] | None,
    zoom: int,
    route_time_gap_min: int,
    route_dist_gap_m: int,
    preloaded_points_desc: list[dict[str, Any]] | None = None,
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
    cached = _cache_get(_TRACK_CONTEXT_CACHE, cache_key, ttl=_TRACK_CONTEXT_CACHE_TTL)
    if cached:
        return cached[1]

    now = time.time()
    if preloaded_points_desc is not None:
        points_desc = preloaded_points_desc
    elif bbox:
        points_desc = storage.list_points_in_bbox(filters, bbox=bbox)
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
    _cache_put(_TRACK_CONTEXT_CACHE, cache_key, (now, context), ttl=_TRACK_CONTEXT_CACHE_TTL, max_items=_LAYER_CACHE_MAX)
    return context


def _resolve_track_layers(
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
    cached = _cache_get(_TRACK_LAYER_CACHE, cache_key, ttl=_TRACK_LAYER_CACHE_TTL)
    if cached:
        return cached[1]

    now = time.time()
    points_desc = track_context["points_desc"]
    points_asc = track_context["points_asc"]
    segments = track_context["segments"]
    result = {
        "context_points_desc": points_desc,
        "segment_count": len(segments),
        "polylines": _serialize_polyline_segments(segments, zoom=zoom, include_labels=include_labels)
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
        "snap": _serialize_snap_segments(segments, zoom=zoom) if include_snap else [],
    }
    _cache_put(_TRACK_LAYER_CACHE, cache_key, (now, result), ttl=_TRACK_LAYER_CACHE_TTL, max_items=_LAYER_CACHE_MAX)
    return result


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


def _serialize_snap_segments(segments: list[list[dict[str, Any]]], *, zoom: int) -> list[dict[str, Any]]:
    snapped = []
    for segment in segments[:10]:
        coords = _snap_segment(segment, zoom=zoom)
        if coords:
            snapped.append({"coords": coords})
    return snapped


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
) -> list[dict[str, Any]]:
    if not points_asc:
        return []
    markers: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
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


def _snap_segment(segment: list[dict[str, Any]], *, zoom: int) -> list[list[float]] | None:
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
    cached = _cache_get(_SNAP_CACHE, key, ttl=_SNAP_CACHE_TTL)
    if cached:
        return cached[1]
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
    _cache_put(_SNAP_CACHE, key, (now, result), ttl=_SNAP_CACHE_TTL, max_items=_SNAP_CACHE_MAX)
    return result


def _request_metadata(request: Request) -> RequestMetadata:
    return RequestMetadata(
        request_id=request.state.request_id,
        received_at_utc=request.state.received_at_utc,
        remote_addr=request.state.remote_addr,
        proxied_ip=request.state.proxied_ip,
        user_agent=request.state.user_agent,
        request_path=request.url.path,
        request_method=request.method,
    )


def _proxied_ip(request: Request, trust_proxy_headers: bool) -> str:
    if not trust_proxy_headers:
        return ""
    header = request.headers.get("x-forwarded-for", "")
    return header.split(",")[0].strip() if header else ""


def _direct_remote_addr(request: Request) -> str:
    return request.client.host if request.client else ""


def _log_request(*, request: Request, status_code: int, duration_ms: float) -> None:
    payload = {
        "event": "http_request",
        "request_id": request.state.request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "remote_ip": request.state.remote_addr,
        "forwarded_ip": request.state.proxied_ip,
        "user_agent": request.state.user_agent,
    }
    payload.update(request.state.log_fields)
    LOGGER.info(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _json_error(
    *,
    request: Request,
    status_code: int,
    detail: str,
    error_category: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "status": "error",
        "requestId": request.state.request_id,
        "error": {"category": error_category, "detail": detail},
    }
    if extra:
        payload["error"].update(extra)
    response = JSONResponse(status_code=status_code, content=payload)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _build_session_signing_key(settings: Settings, existing_key: bytes | None = None) -> bytes:
    if settings.session_signing_secret:
        return settings.session_signing_secret.encode("utf-8")
    if settings.bearer_token:
        return settings.bearer_token.encode("utf-8")
    if settings.admin_password:
        return settings.admin_password.encode("utf-8")
    if existing_key:
        return existing_key
    return secrets.token_bytes(32)


def _create_session_token(settings: Settings, app: FastAPI) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(app.state.session_signing_key, ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}:{sig}"


def _validate_session_token(token: str, settings: Settings, app: FastAPI) -> bool:
    try:
        ts_str, sig = token.split(":", 1)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False
    if time.time() - ts > _SESSION_MAX_AGE:
        return False
    expected = hmac.new(app.state.session_signing_key, ts_str.encode(), hashlib.sha256).hexdigest()
    return compare_digest(sig, expected)


async def _require_bearer_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    settings = _settings(request)
    if not settings.auth_required:
        return
    expected = settings.bearer_token or ""
    scheme, _, supplied_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied_token or not compare_digest(supplied_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _apply_rate_limit(request: Request) -> None:
    limiter: SimpleRateLimiter = request.app.state.rate_limiter
    key = request.state.proxied_ip or request.state.remote_addr or "unknown"
    if not limiter.check(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded.")


async def _require_admin_access(request: Request, authorization: str | None = Header(default=None)) -> None:
    settings = _settings(request)

    # 1. Session-Cookie — gilt für alle Zugriffspfade
    cookie = request.cookies.get(_SESSION_COOKIE, "")
    if cookie and _validate_session_token(cookie, settings, request.app):
        return

    # 2. HTTP-Basic-Auth (wenn Admin-Credentials konfiguriert)
    if settings.admin_auth_enabled:
        scheme, _, encoded = (authorization or "").partition(" ")
        if scheme.lower() != "basic" or not encoded:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin authentication required.",
                headers={"WWW-Authenticate": "Basic"},
            )
        try:
            username, password = b64decode(encoded).decode("utf-8").split(":", 1)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin credentials.",
                headers={"WWW-Authenticate": "Basic"},
            ) from exc
        if not (
            compare_digest(username, settings.admin_username or "")
            and compare_digest(password, settings.admin_password or "")
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin credentials.",
                headers={"WWW-Authenticate": "Basic"},
            )
        return

    # 3. Lokaler Zugriff
    if _is_local_operator_request(
        request.state.remote_addr,
        request.url.hostname,
        request.headers.get("host", ""),
    ):
        return

    # 4. Dashboard-Routen → Login-Redirect statt 403
    if request.url.path.startswith("/dashboard"):
        raise _LoginRequired()

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Dashboard is local-only until admin credentials are configured.",
    )


async def _record_failure(*, request: Request, http_status: int, error_category: str, error_detail: str) -> None:
    if request.url.path != "/live-location":
        return
    partial = _parse_partial_payload(request.state.raw_body_text)
    _storage(request).record_failure(
        metadata=_request_metadata(request),
        ingest_status="failed",
        http_status=http_status,
        error_category=error_category,
        error_detail=error_detail,
        raw_payload_text=request.state.raw_body_text,
        source=partial.get("source"),
        session_id=partial.get("sessionID"),
        capture_mode=partial.get("captureMode"),
        sent_at_utc=partial.get("sentAt"),
        points_count=partial.get("pointsCount", 0),
        first_point_ts_utc=partial.get("firstPointTimestamp"),
        last_point_ts_utc=partial.get("lastPointTimestamp"),
    )
    request.state.log_fields = {
        "error_category": error_category,
        "http_status": http_status,
        "session_id": partial.get("sessionID", ""),
        "capture_mode": partial.get("captureMode", ""),
        "source": partial.get("source", ""),
        "points_count": partial.get("pointsCount", 0),
        "storage_target": str(_storage(request).sqlite_path),
    }


def _parse_partial_payload(raw_payload_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload_text) if raw_payload_text else {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    points = payload.get("points") if isinstance(payload.get("points"), list) else []
    first_ts = points[0].get("timestamp") if points and isinstance(points[0], dict) else None
    last_ts = points[-1].get("timestamp") if points and isinstance(points[-1], dict) else None
    return {
        "source": payload.get("source"),
        "sessionID": payload.get("sessionID"),
        "captureMode": payload.get("captureMode"),
        "sentAt": payload.get("sentAt"),
        "pointsCount": len(points),
        "firstPointTimestamp": first_ts,
        "lastPointTimestamp": last_ts,
    }


def _config_explanations() -> list[dict[str, str]]:
    return [
        {
            "label": "Endpoint",
            "text": "POST /live-location accepts live GPS points from a client that already decided to upload them.",
        },
        {
            "label": "Bearer token",
            "text": "If configured, the Authorization header must contain a matching Bearer token. The token is stored only in runtime configuration and is never returned in API responses.",
        },
        {
            "label": "401 / 422 / 503 / 500",
            "text": "401 means auth failed, 422 means payload or schema invalid, 503 means storage is not ready, 500 means an unexpected bug escaped normal error handling.",
        },
        {
            "label": "Health vs readiness",
            "text": "Health tells you the process is alive. Readiness tells you whether the receiver can persist points safely right now.",
        },
        {
            "label": "Finding recent points",
            "text": "Use the dashboard point list or GET /api/points. Newest points are shown first and can be filtered by date, time, session, source and capture mode.",
        },
        {
            "label": "Exporting data",
            "text": "GET /api/points can export CSV, JSON or NDJSON by setting the format query parameter.",
        },
    ]


def _base_template_context(
    request: Request,
    *,
    active_nav: str,
    page_title: str,
    page_kicker: str,
    page_description: str,
    snapshot: dict[str, Any],
    page_header_actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    settings = _settings(request)
    started_at_utc = request.app.state.started_at_utc
    return {
        "page_title": page_title,
        "page_kicker": page_kicker,
        "page_description": page_description,
        "page_header_actions": page_header_actions or [],
        "active_nav": active_nav,
        "nav_groups": NAV_GROUPS,
        "snapshot": snapshot,
        "app_version": request.app.version,
        "receiver_summary": _receiver_summary(snapshot, settings, started_at_utc),
        "api_links": [
            {"label": "Health JSON", "href": "/health"},
            {"label": "Readiness JSON", "href": "/readyz"},
            {"label": "Stats API", "href": "/api/stats"},
            {"label": "Config summary", "href": "/api/config-summary"},
        ],
        "config_summary": settings.masked_config_summary(),
        "config_explanations": _config_explanations(),
    }


def _dashboard_snapshot(request: Request) -> dict[str, Any]:
    try:
        return _storage(request).get_dashboard_snapshot()
    except StorageError:
        readiness = asdict(_storage(request).readiness())
        now_utc = datetime.now(timezone.utc)
        return {
            "generatedAtUtc": now_utc.isoformat(),
            "storage": {
                "sqlitePath": readiness["sqlite_path"],
                "rawPayloadNdjsonPath": readiness["raw_ndjson_path"],
                "legacyRequestNdjsonPath": str(_settings(request).legacy_request_ndjson_path),
                "rawPayloadNdjsonEnabled": _settings(request).raw_payload_ndjson_enabled,
                "readiness": readiness,
                "sqliteFile": {"exists": Path(readiness["sqlite_path"]).exists(), "path": readiness["sqlite_path"], "sizeBytes": None, "modifiedAtUtc": None},
                "rawPayloadFile": {"exists": Path(readiness["raw_ndjson_path"]).exists(), "path": readiness["raw_ndjson_path"], "sizeBytes": None, "modifiedAtUtc": None},
            },
            "totals": {
                "totalRequests": 0,
                "acceptedRequests": 0,
                "failedRequests": 0,
                "totalPoints": 0,
                "totalSessions": 0,
                "lastSuccessAt": None,
                "lastFailureAt": None,
                "successRate": 0.0,
                "failureRate": 0.0,
            },
            "periods": {
                "requests24h": 0,
                "requests7d": 0,
                "requestsToday": 0,
                "points24h": 0,
                "points7d": 0,
                "pointsToday": 0,
                "sessions24h": 0,
                "sessions7d": 0,
                "sessionEvents24h": 0,
                "sessionEvents7d": 0,
            },
            "latest": {
                "request": None,
                "success": None,
                "failure": None,
                "firstPoint": None,
                "lastPoint": None,
            },
            "accuracy": {
                "minAccuracyM": None,
                "avgAccuracyM": None,
                "maxAccuracyM": None,
            },
            "lists": {
                "recentRequests": [],
                "recentPoints": [],
                "recentSessions": [],
                "topSessions": [],
                "pointsPerDay": [],
                "requestsPerDay": [],
                "responseCodes": [],
                "sourceDistribution": [],
                "captureModeDistribution": [],
                "errorDistribution": [],
            },
            "status": {
                "hasIssues": True,
                "lastErrorCategory": "storage_not_ready",
                "lastErrorDetail": readiness["message"],
                "lastWarning": readiness["message"],
                "lastHttpStatus": None,
                "lastIngestStatus": None,
            },
            "exports": [
                {"label": "CSV export", "format": "csv", "path": "/api/points?format=csv"},
                {"label": "JSON export", "format": "json", "path": "/api/points?format=json"},
                {"label": "NDJSON export", "format": "ndjson", "path": "/api/points?format=ndjson"},
            ],
        }


def _receiver_summary(snapshot: dict[str, Any], settings: Settings, started_at_utc: datetime) -> dict[str, Any]:
    readiness = snapshot["storage"]["readiness"]
    last_request = snapshot["latest"]["request"]
    return {
        "serviceStatus": "online",
        "healthStatus": "ok",
        "readinessStatus": "ready" if readiness["is_ready"] else "not ready",
        "storageStatus": "writable" if readiness["writable"] else "blocked",
        "authStatus": "aktiv" if settings.auth_required else "inaktiv",
        "adminStatus": "aktiv" if settings.admin_auth_enabled else "local-only",
        "publicHostname": settings.public_hostname,
        "bindAddress": f"{settings.bind_host}:{settings.port}",
        "startedAtUtc": started_at_utc.isoformat(),
        "uptime": _format_duration(int((datetime.now(timezone.utc) - started_at_utc).total_seconds())),
        "attentionState": "attention" if snapshot["status"]["hasIssues"] else "ok",
        "attentionMessage": _receiver_attention_message(snapshot, readiness),
        "lastRequestStatus": last_request["ingest_status"] if last_request else "none",
        "lastRequestCode": last_request["http_status"] if last_request else None,
        "localTimezone": settings.local_timezone,
    }


def _receiver_attention_message(snapshot: dict[str, Any], readiness: dict[str, Any]) -> str:
    last_failure = snapshot["latest"]["failure"]
    if not readiness["is_ready"]:
        return readiness["message"]
    if last_failure:
        category = last_failure.get("error_category") or "unbekannter Fehler"
        return f"Letzter Fehler: {category}"
    return "Keine aktuellen Receiver-Probleme erkannt."


def _point_export_links(filters: PointFilters) -> list[dict[str, str]]:
    return [
        {"label": "CSV exportieren", "href": _points_api_href(filters, "csv")},
        {"label": "JSON exportieren", "href": _points_api_href(filters, "json")},
        {"label": "NDJSON exportieren", "href": _points_api_href(filters, "ndjson")},
    ]


def _points_api_href(filters: PointFilters, export_format: str) -> str:
    params = {
        "date_from": filters.date_from,
        "date_to": filters.date_to,
        "time_from": filters.time_from,
        "time_to": filters.time_to,
        "session_id": filters.session_id,
        "capture_mode": filters.capture_mode,
        "source": filters.source,
        "search": filters.search,
        "format": export_format,
    }
    query = urlencode({key: value for key, value in params.items() if value not in {None, ""}})
    return f"/api/points?{query}" if query else "/api/points"


def _timestamp_summary(value: str | None, local_timezone: str) -> dict[str, str | None]:
    if not value:
        return {"utc": None, "local": None, "relative": "keine Daten"}
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return {"utc": value, "local": value, "relative": "unbekannt"}
    local_dt = dt.astimezone(timezone.utc if local_timezone.upper() == "UTC" else datetime.now().astimezone().tzinfo)
    if local_timezone.upper() != "UTC":
        try:
            from zoneinfo import ZoneInfo

            local_dt = dt.astimezone(ZoneInfo(local_timezone))
        except Exception:
            pass
    return {
        "utc": dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "relative": _relative_time(value),
    }


def _relative_time(value: str | None) -> str:
    if not value:
        return "keine Daten"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return "unbekannt"
    delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    seconds = int(abs(delta.total_seconds()))
    if seconds < 60:
        label = f"{seconds}s"
    elif seconds < 3600:
        label = f"{seconds // 60}m"
    elif seconds < 86400:
        label = f"{seconds // 3600}h"
    else:
        label = f"{seconds // 86400}d"
    return f"vor {label}" if delta.total_seconds() >= 0 else f"in {label}"


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}m {remainder}s"
    if seconds < 86400:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m"
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    return f"{days}d {hours}h"


def _format_bytes(value: int | None) -> str:
    if value in {None, 0}:
        return "0 B"
    size = float(value)
    units = ["B", "KB", "MB", "GB"]
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "0.0%"
    return f"{value:.1f}%"


def _status_tone(value: str | None) -> str:
    if not value:
        return "neutral"
    lowered = value.lower()
    if lowered in {"ready", "ok", "accepted", "online", "writable", "aktiv"}:
        return "success"
    if lowered in {"not ready", "failed", "error", "blocked", "attention"}:
        return "danger"
    if lowered in {"local-only", "warning"}:
        return "warn"
    return "neutral"


def _load_markdown_outline(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = path.name
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            current = {"heading": line[3:].strip(), "items": [], "paragraphs": []}
            sections.append(current)
            continue
        if current is None:
            current = {"heading": "Uebersicht", "items": [], "paragraphs": []}
            sections.append(current)
        if line.startswith("- "):
            current["items"].append(line[2:].strip())
        elif line[0].isdigit() and ". " in line:
            current["items"].append(line.split(". ", 1)[1].strip())
        else:
            current["paragraphs"].append(line)
    return {"title": title, "sections": sections, "path": str(path.relative_to(ROOT_DIR))}


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    candidate = hostname.strip().strip("[]").split(":", 1)[0].lower()
    return candidate in {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_local_operator_request(remote_addr: str, request_hostname: str | None = None, host_header: str = "") -> bool:
    if remote_addr in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    try:
        remote_ip = ip_address(remote_addr)
    except ValueError:
        return False
    if remote_ip.is_loopback:
        return True
    # Docker port publishing to 127.0.0.1 commonly reaches the app from a bridge
    # gateway IP rather than real loopback. Only treat that as local when the
    # request itself still targets a loopback host.
    if (_is_loopback_hostname(request_hostname) or _is_loopback_hostname(host_header)) and remote_ip.is_private:
        return True
    return False


app = create_app()
