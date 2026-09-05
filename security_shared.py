"""Geteiltes Security-Modul für alle selbst gebauten Server-Tools (ytdl-webui,
dashboard, künftig LH2GPX) — Security-Header-Middleware + Rate-Limiting.

Bewusst ohne jeden Bezug zu ytdl-spezifischer Logik, nach demselben Prinzip
wie `auth_shared.py`: eine Datei, per Deployment in jedes Tool kopiert
(siehe `dashboard/deploy.sh`).

Integration in `auth_shared.py::setup_auth()` (NICHT von dieser Datei
selbst vorgenommen — nur vorbereitet):

1. Import am Dateikopf von `auth_shared.py` ergänzen:
       from security_shared import login_rate_limit

2. Den Login-Endpoint um den Decorator ergänzen (direkt über der
   bestehenden `@app.post("/api/auth/login")`-Zeile, Decorator-Reihenfolge
   beachten — `login_rate_limit` muss NACH der Routen-Registrierung, also
   näher an der Funktion, respektive slowapi verlangt zusätzlich einen
   `request: Request`-Parameter, der hier bereits vorhanden ist):

       @app.post("/api/auth/login")
       @login_rate_limit("5/minute")
       async def login(body: LoginRequest, request: Request) -> JSONResponse:
           ...

   slowapi liest die Rate-Limit-Identität aus `request` per
   `get_remote_address` (siehe unten) — daher muss `request: Request` in
   der Signatur vorhanden sein und slowapi braucht Zugriff auf
   `app.state.limiter`. Das geschieht zentral über
   `setup_security_headers()`, das `app.state.limiter = limiter` setzt und
   den `RateLimitExceeded`-Exception-Handler registriert. Ruft ein
   server.py sowohl `setup_auth(app, ...)` als auch
   `setup_security_headers(app, ...)` auf, MUSS `setup_security_headers()`
   VOR `setup_auth()` laufen, damit `app.state.limiter` beim Import des
   `login_rate_limit`-Decorators bereits existiert (der Decorator selbst
   verzögert den Limiter-Zugriff nicht — er nutzt beim Modul-Import die
   globale `limiter`-Instanz aus diesem Modul, das ist unabhängig von der
   Aufrufreihenfolge; nur der Exception-Handler in `setup_security_headers()`
   muss vor dem ersten Request registriert sein, Aufrufreihenfolge der
   beiden setup_*-Funktionen ist also in der Praxis egal, solange beide vor
   `app.run`/`uvicorn.run` erfolgen).

   Zusätzliche Abhängigkeit: `slowapi` (siehe requirements.txt) — geprüft
   per `pip index versions slowapi` (0.1.10 verfügbar, reine Python-Lib,
   keine bekannte Versionsobergrenze) und lokal noch NICHT installiert
   (weder systemweit noch in den drei .venv-Verzeichnissen unter
   `~/services/`) — vor dem ersten Deploy `pip install slowapi` in jedem
   betroffenen venv nachholen.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

# Geteilte Limiter-Instanz — ein Prozess pro Tool, daher reicht die
# In-Memory-Standardstrategie von slowapi (kein Redis-Backend nötig, siehe
# auch `auth_shared.py`-Docstring zum selben Trade-off bei Sessions, dort
# aber bewusst SQLite statt In-Memory, weil Sessions prozessübergreifend
# gelten müssen — Login-Rate-Limits dagegen dürfen pro Prozess zählen).
limiter = Limiter(key_func=get_remote_address)

# Wiederverwendbarer Decorator für die Login-Route — siehe Modul-Docstring
# oben für die exakte Integration in `auth_shared.py::setup_auth()`.
login_rate_limit = limiter.limit


def setup_security_headers(
    app: FastAPI,
    *,
    permissions_policy: str = "geolocation=()",
    extra_csp_connect_src: list[str] | None = None,
) -> None:
    """Registriert die Security-Header-Middleware sowie den slowapi-
    Limiter (inkl. Exception-Handler für 429) auf `app`. Ein Aufruf pro
    FastAPI-App, analog zu `auth_shared.py::setup_auth()`.

    `permissions_policy`: Default sperrt Geolocation für alle Tools außer
    LH2GPX (dort `geolocation=(self)` übergeben, siehe Phase-1-Plan).
    `extra_csp_connect_src`: zusätzliche `connect-src`-Quellen (z.B. für
    externe APIs), werden an `'self' wss:` angehängt.
    """
    connect_src = "'self' wss:"
    if extra_csp_connect_src:
        connect_src = " ".join([connect_src, *extra_csp_connect_src])
    csp_report_only = (
        f"default-src 'self'; frame-ancestors 'self'; "
        f"form-action 'self'; connect-src {connect_src}"
    )

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            response = await call_next(request)
            # Zunächst NUR Report-Only — noch nicht enforcing, siehe
            # Phase-1-Plan: erst einige Tage CSP-Verletzungen in der
            # Browser-Konsole beobachten, bevor Phase 2 auf enforcing
            # umstellt.
            response.headers["Content-Security-Policy-Report-Only"] = csp_report_only
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = permissions_policy
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # Rate-Limiting-Infrastruktur (slowapi): State + Exception-Handler
    # müssen vor dem ersten Request gesetzt sein, damit `login_rate_limit`
    # (siehe Modul-Docstring) auf der Login-Route greift.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
