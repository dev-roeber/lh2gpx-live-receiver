-- LH2GPX Web Push/VAPID foundation, v1.
-- Intentionally not imported by app/storage.py. Applying this file is a
-- separate, explicit operator action after the delivery implementation,
-- consent flow and recovery procedure have been reviewed.
-- This schema stores no VAPID keys and performs no registration or delivery.
PRAGMA foreign_keys = ON;

BEGIN;

-- PushSubscription endpoint and encryption keys are bearer-like credentials.
-- They must be protected with the database file and never be logged or
-- returned in ordinary UI responses.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL CHECK (length(trim(user_id)) > 0),
    endpoint TEXT NOT NULL UNIQUE CHECK (length(trim(endpoint)) > 0),
    p256dh_key TEXT NOT NULL CHECK (length(trim(p256dh_key)) > 0),
    auth_key TEXT NOT NULL CHECK (length(trim(auth_key)) > 0),
    user_agent TEXT,
    created_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT,
    revoked_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS push_delivery_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL REFERENCES push_subscriptions(subscription_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (length(trim(event_type)) > 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'expired', 'revoked')),
    response_code INTEGER,
    attempted_at_utc TEXT NOT NULL,
    error_code TEXT,
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_active
    ON push_subscriptions(user_id, revoked_at_utc);
CREATE INDEX IF NOT EXISTS idx_push_delivery_attempts_subscription_time
    ON push_delivery_attempts(subscription_id, attempted_at_utc DESC);

COMMIT;
