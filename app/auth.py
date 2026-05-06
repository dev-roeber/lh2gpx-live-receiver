from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from base64 import b64decode
from ipaddress import ip_address
from secrets import compare_digest

from fastapi import FastAPI, Header, HTTPException, Request, status

from .config import Settings


SESSION_COOKIE = "lh2gpx_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 Tage


class LoginRequired(Exception):
    """Raised for HTML dashboard routes that need a login redirect."""


def build_session_signing_key(settings: Settings, existing_key: bytes | None = None) -> bytes:
    if settings.session_signing_secret:
        return settings.session_signing_secret.encode("utf-8")
    if settings.bearer_token:
        return settings.bearer_token.encode("utf-8")
    if settings.admin_password:
        return settings.admin_password.encode("utf-8")
    if existing_key:
        return existing_key
    return secrets.token_bytes(32)


def create_session_token(app: FastAPI) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(app.state.session_signing_key, ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}:{sig}"


def validate_session_token(token: str, app: FastAPI) -> bool:
    try:
        ts_str, sig = token.split(":", 1)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False
    if time.time() - ts > SESSION_MAX_AGE:
        return False
    expected = hmac.new(app.state.session_signing_key, ts_str.encode(), hashlib.sha256).hexdigest()
    return compare_digest(sig, expected)


def proxied_ip(request: Request, trust_proxy_headers: bool) -> str:
    if not trust_proxy_headers:
        return ""
    header = request.headers.get("x-forwarded-for", "")
    return header.split(",")[0].strip() if header else ""


def direct_remote_addr(request: Request) -> str:
    return request.client.host if request.client else ""


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


async def require_admin_access(request: Request, authorization: str | None = Header(default=None)) -> None:
    settings: Settings = request.app.state.settings

    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie and validate_session_token(cookie, request.app):
        return

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
        detail="Dashboard is local-only until admin credentials are configured.",
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
