"""Durable, direct PostgreSQL change sync from Dawarich to receiver SQLite."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone

import psycopg

from .config import Settings
from .storage import ReceiverStorage

LOGGER = logging.getLogger("lh2gpx-dawarich-sync")
CHANNEL = "dawarich_points_changed"
BATCH_SIZE = 500


def _dsn(settings: Settings) -> str:
    password = settings.dawarich_db_password or os.getenv("POSTGRES_PASSWORD", "")
    return "host={host} port={port} dbname={name} user={user} password={password}".format(
        host=settings.dawarich_db_host, port=settings.dawarich_db_port,
        name=settings.dawarich_db_name, user=settings.dawarich_db_user, password=password,
    )


def _fetch_points(conn: psycopg.Connection, ids: list[int] | None = None, offset: int = 0) -> list[dict]:
    if ids is not None:
        if not ids:
            return []
        rows = conn.execute(
            """SELECT id, user_id, timestamp::bigint AS timestamp,
            ST_Y(lonlat::geometry) AS latitude, ST_X(lonlat::geometry) AS longitude,
            accuracy, altitude, velocity, tracker_id, import_id, updated_at
            FROM points WHERE id = ANY(%s) AND lonlat IS NOT NULL ORDER BY id""", (ids,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, user_id, timestamp::bigint AS timestamp,
            ST_Y(lonlat::geometry) AS latitude, ST_X(lonlat::geometry) AS longitude,
            accuracy, altitude, velocity, tracker_id, import_id, updated_at
            FROM points WHERE lonlat IS NOT NULL ORDER BY id LIMIT %s OFFSET %s""", (BATCH_SIZE, offset)
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["updated_at"] = item["updated_at"].isoformat() if item.get("updated_at") else None
        item["payload_hash"] = hashlib.sha1(repr(sorted(item.items())).encode()).hexdigest()
        result.append(item)
    return result


def _process_events(conn: psycopg.Connection, storage: ReceiverStorage, cursor: int) -> int:
    events = conn.execute(
        """SELECT id, operation, record_id FROM receiver_sync_events
        WHERE table_name='points' AND id > %s ORDER BY id LIMIT %s""", (cursor, BATCH_SIZE)
    ).fetchall()
    if not events:
        return cursor
    upserts: list[dict] = []
    deletes: list[str] = []
    for event in events:
        if event["operation"] == "delete":
            deletes.append(str(event["record_id"]))
        else:
            fetched = _fetch_points(conn, [int(event["record_id"])])
            upserts.extend(fetched)
            if not fetched:
                deletes.append(str(event["record_id"]))
    storage.upsert_dawarich_points(upserts)
    storage.delete_dawarich_points(deletes)
    new_cursor = max(int(event["id"]) for event in events)
    storage.set_dawarich_sync_state(
        last_event_id=new_cursor,
        last_success_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    return new_cursor


def run() -> None:
    settings = Settings.from_env()
    storage = ReceiverStorage(settings)
    storage.startup()
    if not storage.readiness().is_ready:
        raise RuntimeError("Receiver storage is not ready")
    cursor = int(storage.get_dawarich_sync_state().get("last_event_id") or 0)
    while True:
        try:
            with psycopg.connect(_dsn(settings), row_factory=psycopg.rows.dict_row, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                if cursor == 0:
                    barrier = int(conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM receiver_sync_events").fetchone()["max_id"])
                    offset = 0
                    while True:
                        batch = _fetch_points(conn, offset=offset)
                        if not batch:
                            break
                        storage.upsert_dawarich_points(batch, rebuild=False)
                        offset += len(batch)
                    storage.rebuild_derived_data()
                    cursor = barrier
                    storage.set_dawarich_sync_state(last_event_id=cursor, last_success_at=datetime.now(timezone.utc).isoformat(), last_error=None)
                while True:
                    cursor = _process_events(conn, storage, cursor)
                    # The durable outbox is authoritative.  Polling also covers
                    # missed NOTIFY messages and avoids a busy loop on psycopg
                    # versions where notifies() does not block as expected.
                    time.sleep(1)
        except Exception as exc:
            LOGGER.exception("Dawarich sync connection/processing failed: %s", exc)
            storage.set_dawarich_sync_state(last_event_id=cursor, last_error=f"{type(exc).__name__}: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
