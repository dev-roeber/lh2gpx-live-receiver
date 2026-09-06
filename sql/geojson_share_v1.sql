-- LH2GPX GeoJSON share-link foundation, v1.
-- Intentionally not imported by app/storage.py. Applying this file is a
-- separate, explicit action after the route, snapshot, revocation and
-- cleanup implementation has been reviewed.
-- The raw token is never stored in this schema.
PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS geojson_shares (
    share_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_by_user_id TEXT NOT NULL CHECK (length(trim(created_by_user_id)) > 0),
    scope_json TEXT NOT NULL,
    snapshot_path TEXT NOT NULL,
    point_count INTEGER NOT NULL CHECK (point_count >= 0),
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT,
    max_downloads INTEGER NOT NULL DEFAULT 10 CHECK (max_downloads > 0),
    download_count INTEGER NOT NULL DEFAULT 0 CHECK (download_count >= 0),
    last_download_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_geojson_shares_active
    ON geojson_shares(revoked_at_utc, expires_at_utc);

COMMIT;
