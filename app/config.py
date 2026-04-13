import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


def _read_timezone_env(name: str, *, default: str) -> str:
    value = _read_non_empty_env(name, default=default)
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"{name} must be a valid IANA timezone, got {value!r}.") from exc
    return value


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
        base = cls._from_env_base(data_dir)
        return base.with_persistent_overrides()

    @classmethod
    def _from_env_base(cls, data_dir: Path) -> "Settings":
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
            local_timezone=_read_timezone_env("LOCAL_TIMEZONE", default="UTC"),
            log_level=_read_non_empty_env("LOG_LEVEL", default="INFO").upper(),
            request_body_max_bytes=_read_int_env("REQUEST_BODY_MAX_BYTES", default=262144, minimum=1024),
            points_page_size_default=_read_int_env("POINTS_PAGE_SIZE_DEFAULT", default=50, minimum=1, maximum=500),
            points_page_size_max=_read_int_env("POINTS_PAGE_SIZE_MAX", default=250, minimum=1, maximum=2000),
            rate_limit_requests_per_minute=_read_int_env("RATE_LIMIT_REQUESTS_PER_MINUTE", default=0, minimum=0),
            trust_proxy_headers=_read_bool_env("TRUST_PROXY_HEADERS", default=True),
        )

    def with_persistent_overrides(self) -> "Settings":
        path = self.persistent_settings_path
        if not path.exists():
            return self
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            valid_keys = {
                "public_hostname", "public_base_url", "bearer_token", 
                "raw_payload_ndjson_enabled", "local_timezone", "log_level",
                "points_page_size_default", "points_page_size_max"
            }
            overrides = {k: v for k, v in data.items() if k in valid_keys and v is not None}
            if not overrides:
                return self
            return replace(self, **overrides)
        except Exception:
            return self

    @property
    def persistent_settings_path(self) -> Path:
        return self.data_dir / "persistent-settings.json"

    def save_persistent(self, updates: dict[str, object]) -> None:
        # Validierung vor dem Speichern
        if "local_timezone" in updates:
            try:
                ZoneInfo(str(updates["local_timezone"]))
            except Exception:
                raise ValueError(f"Ungültige Zeitzone: {updates['local_timezone']}")
        
        if "public_base_url" in updates:
            url = str(updates["public_base_url"])
            if not url.startswith(("http://", "https://")):
                raise ValueError("Basis-URL muss mit http:// oder https:// beginnen")

        path = self.persistent_settings_path
        current_data = {}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    current_data = json.load(f)
            except Exception:
                pass
        
        # Nur erlaubte Felder updaten
        allowed_fields = {
            "public_hostname", "public_base_url", "bearer_token", 
            "raw_payload_ndjson_enabled", "local_timezone", "log_level",
            "points_page_size_default", "points_page_size_max"
        }
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        current_data.update(filtered_updates)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(current_data, f, indent=2)

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
