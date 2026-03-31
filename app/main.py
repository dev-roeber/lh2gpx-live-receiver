from __future__ import annotations

import json
import logging
import time
from base64 import b64decode
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from secrets import compare_digest
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings
from .models import LiveLocationRequest, PointFilters, RequestFilters, RequestMetadata
from .storage import ReceiverStorage, StorageError


LOGGER = logging.getLogger("lh2gpx_live_receiver")
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


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


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    _configure_logging(resolved_settings.log_level)

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    app = FastAPI(title="LH2GPX Live Location Receiver", version="0.3.0")
    app.state.settings = resolved_settings
    app.state.storage = ReceiverStorage(resolved_settings)
    app.state.storage.startup()
    app.state.rate_limiter = SimpleRateLimiter(resolved_settings.rate_limit_requests_per_minute)
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
            if len(raw_body) > resolved_settings.request_body_max_bytes:
                response = _json_error(
                    request=request,
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body exceeds {resolved_settings.request_body_max_bytes} bytes.",
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
    async def storage_exception_handler(request: Request, exc: StorageError) -> JSONResponse:
        await _record_failure(
            request=request,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_category=exc.error_category,
            error_detail=str(exc),
        )
        return _json_error(
            request=request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.public_message,
            error_category=exc.error_category,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if request.url.path == "/live-location" and exc.status_code in {401, 429}:
            await _record_failure(
                request=request,
                http_status=exc.status_code,
                error_category="authentication_failed" if exc.status_code == 401 else "rate_limited",
                error_detail=str(exc.detail),
            )
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
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        await _record_failure(
            request=request,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_category="unexpected_internal_error",
            error_detail=repr(exc),
        )
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
        return {"status": "accepted", "requestId": metadata.request_id, **storage_summary}

    @app.get("/api/stats", dependencies=[Depends(_require_admin_access)])
    async def api_stats(request: Request) -> dict[str, Any]:
        return {"requestId": request.state.request_id, "stats": _storage(request).get_stats()}

    @app.get("/api/config-summary", dependencies=[Depends(_require_admin_access)])
    async def api_config_summary(request: Request) -> dict[str, Any]:
        return {
            "requestId": request.state.request_id,
            "config": _settings(request).masked_config_summary(),
            "readiness": asdict(_storage(request).readiness()),
            "explanations": _config_explanations(),
        }

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
        if format not in {"json", "csv", "ndjson"}:
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
        return {"requestId": request.state.request_id, "points": _storage(request).list_points(filters)}

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

    @app.get("/admin", include_in_schema=False)
    async def admin_redirect() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

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
        points = _storage(request).list_points(point_filters)
        recent_requests = _storage(request).list_requests(RequestFilters(page=1, page_size=10))
        sessions = _storage(request).list_sessions()[:10]
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "page_title": "Receiver dashboard",
                "stats": _storage(request).get_stats(),
                "points": points,
                "points_items": points["items"],
                "recent_requests": recent_requests["items"],
                "sessions": sessions,
                "filters": point_filters,
                "config_summary": _settings(request).masked_config_summary(),
                "config_explanations": _config_explanations(),
                "readiness": asdict(_storage(request).readiness()),
            },
        )

    @app.get("/dashboard/requests/{request_id}", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_request_detail(request: Request, request_id: str) -> HTMLResponse:
        item = _storage(request).get_request(request_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
        return templates.TemplateResponse(
            request=request,
            name="request_detail.html",
            context={"page_title": f"Request {request_id}", "request_item": item},
        )

    @app.get("/dashboard/sessions/{session_id}", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_require_admin_access)])
    async def dashboard_session_detail(request: Request, session_id: str) -> HTMLResponse:
        item = _storage(request).get_session(session_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        return templates.TemplateResponse(
            request=request,
            name="session_detail.html",
            context={"page_title": f"Session {session_id}", "session_item": item},
        )

    return app


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", force=True)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _storage(request: Request) -> ReceiverStorage:
    return request.app.state.storage


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

    if not _is_local_operator_request(request.state.remote_addr, request.state.proxied_ip):
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


def _is_local_operator_request(remote_addr: str, proxied_ip: str) -> bool:
    if proxied_ip:
        return proxied_ip in {"127.0.0.1", "::1", "localhost", "testclient"}
    if remote_addr in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    try:
        return ip_address(remote_addr).is_private
    except ValueError:
        return False


app = create_app()
