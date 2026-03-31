from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LiveLocationPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timestamp: datetime
    horizontalAccuracyM: float = Field(ge=0)


class LiveLocationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = Field(min_length=1)
    sessionID: UUID
    captureMode: str = Field(min_length=1)
    sentAt: datetime
    points: list[LiveLocationPoint] = Field(min_length=1)

    @field_validator("source", "captureMode")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Value must not be blank.")
        return trimmed


@dataclass(slots=True)
class RequestMetadata:
    request_id: str
    received_at_utc: datetime
    remote_addr: str
    proxied_ip: str
    user_agent: str
    request_path: str
    request_method: str


@dataclass(slots=True)
class PointFilters:
    date_from: str | None = None
    date_to: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    session_id: str | None = None
    capture_mode: str | None = None
    source: str | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 50


@dataclass(slots=True)
class RequestFilters:
    date_from: str | None = None
    date_to: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    session_id: str | None = None
    capture_mode: str | None = None
    source: str | None = None
    ingest_status: str | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 50


def payload_to_json(payload: LiveLocationRequest) -> dict[str, Any]:
    return payload.model_dump(mode="json")
