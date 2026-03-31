from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_non_empty_env(name: str, *, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty.")
    return value


def _read_int_env(name: str, *, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}.")
    return value


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name, "true" if default else "false").strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got {raw_value!r}.")


@dataclass(frozen=True)
class Settings:
    bind_host: str
    port: int
    public_hostname: str
    public_base_url: str
    bearer_token: str | None
    admin_username: str | None
    admin_password: str | None
    data_dir: Path
    sqlite_path: Path
    raw_payload_ndjson_path: Path
    legacy_request_ndjson_path: Path
    raw_payload_ndjson_enabled: bool
    local_timezone: str
    log_level: str
    request_body_max_bytes: int
    points_page_size_default: int
    points_page_size_max: int
    rate_limit_requests_per_minute: int
    trust_proxy_headers: bool

    @property
    def auth_required(self) -> bool:
        return bool(self.bearer_token)

    @property
    def admin_auth_enabled(self) -> bool:
        return bool(self.admin_username and self.admin_password)

    @property
    def dashboard_enabled(self) -> bool:
        return True

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_read_non_empty_env("DATA_DIR", default="/app/data"))
        sqlite_path = Path(
            _read_non_empty_env(
                "SQLITE_PATH",
                default=str(data_dir / "receiver.sqlite3"),
            )
        )
        raw_payload_ndjson_path = Path(
            _read_non_empty_env(
                "RAW_PAYLOAD_NDJSON_PATH",
                default=str(data_dir / "raw-payloads.ndjson"),
            )
        )
        legacy_request_ndjson_path = Path(
            _read_non_empty_env(
                "LEGACY_REQUEST_NDJSON_PATH",
                default=str(data_dir / "live-location.ndjson"),
            )
        )

        raw_bearer_token = os.getenv("LIVE_LOCATION_BEARER_TOKEN", "").strip()
        raw_admin_username = os.getenv("ADMIN_USERNAME", "").strip()
        raw_admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

        return cls(
            bind_host=_read_non_empty_env("BIND_HOST", default="0.0.0.0"),
            port=_read_int_env("PORT", default=8080, minimum=1, maximum=65535),
            public_hostname=_read_non_empty_env("PUBLIC_HOSTNAME", default="localhost"),
            public_base_url=_read_non_empty_env("PUBLIC_BASE_URL", default="http://localhost:8080"),
            bearer_token=raw_bearer_token or None,
            admin_username=raw_admin_username or None,
            admin_password=raw_admin_password or None,
            data_dir=data_dir,
            sqlite_path=sqlite_path,
            raw_payload_ndjson_path=raw_payload_ndjson_path,
            legacy_request_ndjson_path=legacy_request_ndjson_path,
            raw_payload_ndjson_enabled=_read_bool_env("ENABLE_RAW_PAYLOAD_NDJSON", default=True),
            local_timezone=_read_non_empty_env("LOCAL_TIMEZONE", default="UTC"),
            log_level=_read_non_empty_env("LOG_LEVEL", default="INFO").upper(),
            request_body_max_bytes=_read_int_env("REQUEST_BODY_MAX_BYTES", default=262144, minimum=1024),
            points_page_size_default=_read_int_env("POINTS_PAGE_SIZE_DEFAULT", default=50, minimum=1, maximum=500),
            points_page_size_max=_read_int_env("POINTS_PAGE_SIZE_MAX", default=250, minimum=1, maximum=2000),
            rate_limit_requests_per_minute=_read_int_env("RATE_LIMIT_REQUESTS_PER_MINUTE", default=0, minimum=0),
            trust_proxy_headers=_read_bool_env("TRUST_PROXY_HEADERS", default=True),
        )

    def masked_config_summary(self) -> dict[str, object]:
        return {
            "bindHost": self.bind_host,
            "port": self.port,
            "publicHostname": self.public_hostname,
            "publicBaseUrl": self.public_base_url,
            "authRequired": self.auth_required,
            "bearerToken": _mask_secret(self.bearer_token),
            "adminAuthEnabled": self.admin_auth_enabled,
            "adminUsername": self.admin_username or "",
            "adminPassword": _mask_secret(self.admin_password),
            "dataDir": str(self.data_dir),
            "sqlitePath": str(self.sqlite_path),
            "rawPayloadNdjsonEnabled": self.raw_payload_ndjson_enabled,
            "rawPayloadNdjsonPath": str(self.raw_payload_ndjson_path),
            "legacyRequestNdjsonPath": str(self.legacy_request_ndjson_path),
            "localTimezone": self.local_timezone,
            "logLevel": self.log_level,
            "requestBodyMaxBytes": self.request_body_max_bytes,
            "pointsPageSizeDefault": self.points_page_size_default,
            "pointsPageSizeMax": self.points_page_size_max,
            "rateLimitRequestsPerMinute": self.rate_limit_requests_per_minute,
            "trustProxyHeaders": self.trust_proxy_headers,
        }


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return f"set(len={len(value)})"
