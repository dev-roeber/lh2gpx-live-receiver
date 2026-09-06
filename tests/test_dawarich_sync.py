from __future__ import annotations

import pytest

from app import dawarich_sync


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Result:
        self.query = query
        self.params = params
        return _Result(self.rows)


def test_initial_point_fetch_uses_bounded_keyset() -> None:
    connection = _Connection([])

    assert dawarich_sync._fetch_points(connection, after_id=500, max_id=1200) == []

    assert "OFFSET" not in connection.query.upper()
    assert "id > %s" in connection.query
    assert "id <= %s" in connection.query
    assert "ORDER BY id" in connection.query
    assert connection.params == (500, 1200, dawarich_sync.BATCH_SIZE)


def test_initial_point_fetch_requires_stable_barrier() -> None:
    connection = _Connection([])

    with pytest.raises(ValueError, match="max_id is required"):
        dawarich_sync._fetch_points(connection, after_id=500)

    assert connection.query == ""
