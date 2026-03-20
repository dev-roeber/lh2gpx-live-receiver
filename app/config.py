from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bind_host: str
    port: int
    bearer_token: str | None
    data_dir: Path
    log_level: str

    @property
    def data_file(self) -> Path:
        return self.data_dir / "live-location.ndjson"

    @property
    def auth_required(self) -> bool:
        return bool(self.bearer_token)

    @classmethod
    def from_env(cls) -> "Settings":
        bind_host = _read_non_empty_env("BIND_HOST", default="0.0.0.0")
        port = _read_int_env("PORT", default=8080)
        data_dir = Path(_read_non_empty_env("DATA_DIR", default="data"))
        log_level = _read_non_empty_env("LOG_LEVEL", default="INFO").upper()

        raw_token = os.getenv("LIVE_LOCATION_BEARER_TOKEN", "").strip()
        bearer_token = raw_token or None

        return cls(
            bind_host=bind_host,
            port=port,
            bearer_token=bearer_token,
            data_dir=data_dir,
            log_level=log_level,
        )


def _read_non_empty_env(name: str, *, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty.")
    return value


def _read_int_env(name: str, *, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}.") from exc
    if value <= 0 or value > 65535:
        raise ValueError(f"{name} must be between 1 and 65535, got {value}.")
    return value

