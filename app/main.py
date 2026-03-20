from __future__ import annotations

import logging
from datetime import datetime, timezone
from secrets import compare_digest

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status

from .config import Settings
from .models import LiveLocationRequest
from .storage import NDJSONStorage


LOGGER = logging.getLogger("lh2gpx_live_receiver")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    _configure_logging(resolved_settings.log_level)

    app = FastAPI(title="LH2GPX Live Location Receiver", version="0.1.0")
    app.state.settings = resolved_settings
    app.state.storage = NDJSONStorage(resolved_settings.data_file)

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        configured_settings: Settings = request.app.state.settings
        storage: NDJSONStorage = request.app.state.storage
        return {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
            "service": "lh2gpx-live-receiver",
            "authRequired": configured_settings.auth_required,
            "dataFile": str(storage.path),
            "dataFileExists": storage.path.exists(),
        }

    @app.post(
        "/live-location",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(_require_bearer_token)],
    )
    async def receive_live_location(
        payload: LiveLocationRequest,
        request: Request,
        response: Response,
    ) -> dict[str, object]:
        storage: NDJSONStorage = request.app.state.storage
        data_file = storage.append(payload)
        summary = _build_point_log_summary(payload)
        LOGGER.info(
            summary,
        )
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "accepted",
            "pointsAccepted": len(payload.points),
            "dataFile": str(data_file),
        }

    return app


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _build_point_log_summary(payload: LiveLocationRequest) -> str:
    first_point = payload.points[0]
    last_point = payload.points[-1]
    return (
        f"pts={len(payload.points)} "
        f"first={first_point.latitude:.6f},{first_point.longitude:.6f} "
        f"last={last_point.latitude:.6f},{last_point.longitude:.6f} "
        f"firstTs={first_point.timestamp.isoformat()} "
        f"lastTs={last_point.timestamp.isoformat()} "
        f"mode={payload.captureMode} "
        f"session={payload.sessionID} "
        f"source={payload.source}"
    )


async def _require_bearer_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    settings: Settings = request.app.state.settings
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


app = create_app()
