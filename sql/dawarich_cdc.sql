CREATE TABLE IF NOT EXISTS receiver_sync_events (
    id BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id BIGINT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS receiver_sync_events_lookup
    ON receiver_sync_events (table_name, id);

CREATE OR REPLACE FUNCTION receiver_points_change_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    point_id BIGINT;
    operation_name TEXT;
    event_id BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        point_id := OLD.id;
        operation_name := 'delete';
    ELSE
        point_id := NEW.id;
        operation_name := lower(TG_OP);
    END IF;

    INSERT INTO receiver_sync_events(table_name, record_id, operation)
    VALUES ('points', point_id, operation_name)
    RETURNING id INTO event_id;

    PERFORM pg_notify('dawarich_points_changed', event_id::text);
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS receiver_points_change_trigger ON points;
CREATE TRIGGER receiver_points_change_trigger
AFTER INSERT OR UPDATE OR DELETE ON points
FOR EACH ROW EXECUTE FUNCTION receiver_points_change_event();
