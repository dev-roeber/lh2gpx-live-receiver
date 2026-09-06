-- LH2GPX Geofencing foundation, v1.
-- Intentionally not imported by app/storage.py. Applying this file is a
-- separate, explicit operator action after the feature implementation exists.
PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS geofences (
    geofence_id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    geometry_type TEXT NOT NULL CHECK (geometry_type IN ('circle', 'polygon')),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    center_latitude REAL,
    center_longitude REAL,
    radius_m REAL,
    polygon_geojson TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK (
        (geometry_type = 'circle'
         AND center_latitude IS NOT NULL
         AND center_longitude IS NOT NULL
         AND center_latitude BETWEEN -90.0 AND 90.0
         AND center_longitude BETWEEN -180.0 AND 180.0
         AND radius_m IS NOT NULL
         AND radius_m > 0.0
         AND radius_m <= 1000000.0
         AND polygon_geojson IS NULL)
        OR
        (geometry_type = 'polygon'
         AND center_latitude IS NULL
         AND center_longitude IS NULL
         AND radius_m IS NULL
         AND polygon_geojson IS NOT NULL
         AND length(trim(polygon_geojson)) > 0)
    )
);

-- Current inside/outside state per logical subject. The subject key is
-- deliberately independent of gps_points IDs so Dawarich external points and
-- future receiver sources can use the same state table.
CREATE TABLE IF NOT EXISTS geofence_subject_state (
    geofence_id TEXT NOT NULL REFERENCES geofences(geofence_id) ON DELETE CASCADE,
    subject_key TEXT NOT NULL CHECK (length(trim(subject_key)) > 0),
    is_inside INTEGER NOT NULL CHECK (is_inside IN (0, 1)),
    last_point_source TEXT NOT NULL CHECK (last_point_source IN ('receiver', 'dawarich')),
    last_point_key TEXT NOT NULL CHECK (length(trim(last_point_key)) > 0),
    last_point_timestamp_utc TEXT NOT NULL,
    last_latitude REAL NOT NULL CHECK (last_latitude BETWEEN -90.0 AND 90.0),
    last_longitude REAL NOT NULL CHECK (last_longitude BETWEEN -180.0 AND 180.0),
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (geofence_id, subject_key)
);

-- Idempotent transition ledger. This is detection history only; it is not a
-- push queue and has no delivery or notification side effects.
CREATE TABLE IF NOT EXISTS geofence_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    geofence_id TEXT NOT NULL REFERENCES geofences(geofence_id) ON DELETE CASCADE,
    subject_key TEXT NOT NULL CHECK (length(trim(subject_key)) > 0),
    point_source TEXT NOT NULL CHECK (point_source IN ('receiver', 'dawarich')),
    point_key TEXT NOT NULL CHECK (length(trim(point_key)) > 0),
    transition TEXT NOT NULL CHECK (transition IN ('enter', 'exit')),
    point_timestamp_utc TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    detected_at_utc TEXT NOT NULL,
    UNIQUE (geofence_id, subject_key, point_source, point_key, transition)
);

CREATE INDEX IF NOT EXISTS idx_geofence_subject_state_subject
    ON geofence_subject_state(subject_key, updated_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_geofence_transitions_geofence_time
    ON geofence_transitions(geofence_id, point_timestamp_utc DESC);

CREATE INDEX IF NOT EXISTS idx_geofence_transitions_subject_time
    ON geofence_transitions(subject_key, point_timestamp_utc DESC);

COMMIT;
