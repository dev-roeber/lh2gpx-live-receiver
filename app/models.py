from __future__ import annotations

from datetime import datetime
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

