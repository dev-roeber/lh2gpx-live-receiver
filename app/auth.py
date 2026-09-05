from __future__ import annotations

import os
import sqlite3
import time
from ipaddress import ip_address
from secrets import compare_digest
from pathlib import Path

from fastapi import Header, HTTPException, Request, status

from .config import Settings


SHARED_SESSION_COOKIE = "ytdl_session"


class LoginRequired(Exception):
    """Raised for HTML dashboard routes that need a login redirect."""


def proxied_ip(request: Request, trust_proxy_headers: bool) -> str:
    if not trust_proxy_headers:
        return ""
    header = request.headers.get("x-forwarded-for", "")
    return header.split(",")[0].strip() if header else ""


def direct_remote_addr(request: Request) -> str:
    return request.client.host if request.client else ""


def validate_shared_dashboard_session(request: Request) -> str | None:
    """Validate the session created by the central dashboard login.

    The cookie is host-scoped (not port-scoped), so it is available to the
    receiver when it is opened on the same public hostname. The SQLite
    database is shared by dashboard and all first-party tools.
    """
    session_id = request.cookies.get(SHARED_SESSION_COOKIE, "").strip()
    if not session_id:
        return None
    database = Path(os.getenv("DASHBOARD_SESSIONS_DB", str(Path.home() / "services/auth/sessions.db")))
    try:
        with sqlite3.connect(database, timeout=2) as connection:
            row = connection.execute(
                "SELECT username, expires FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            username, expires = row
            if float(expires) < time.time():
                connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                connection.commit()
                return None
            # Keep the central dashboard's sliding-session behaviour.
            connection.execute(
                "UPDATE sessions SET expires = ? WHERE session_id = ?",
                (time.time() + 14 * 24 * 3600, session_id),
            )
            connection.commit()
            return str(username) if username else None
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None


async def require_bearer_token(request: Request, authorization: str | None = Header(default=None)) -> None:
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


async def apply_rate_limit(request: Request) -> None:
    limiter = request.app.state.rate_limiter
    key = request.state.proxied_ip or request.state.remote_addr or "unknown"
    if not limiter.check(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded.")


async def require_admin_access(request: Request) -> None:
    if validate_shared_dashboard_session(request):
        return

    if is_local_operator_request(
        request.state.remote_addr,
        request.url.hostname,
        request.headers.get("host", ""),
    ):
        return

    if request.url.path.startswith("/dashboard"):
        raise LoginRequired()

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Dashboard requires the shared dashboard login or local (loopback) access.",
    )


def is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    candidate = hostname.strip().strip("[]").split(":", 1)[0].lower()
    return candidate in {"127.0.0.1", "::1", "localhost", "testclient"}


def is_local_operator_request(remote_addr: str, request_hostname: str | None = None, host_header: str = "") -> bool:
    if remote_addr in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    try:
        remote_ip = ip_address(remote_addr)
    except ValueError:
        return False
    if remote_ip.is_loopback:
        return True
    if (is_loopback_hostname(request_hostname) or is_loopback_hostname(host_header)) and remote_ip.is_private:
        return True
    return False
