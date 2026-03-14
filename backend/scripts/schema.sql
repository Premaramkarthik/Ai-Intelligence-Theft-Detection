CREATE TABLE IF NOT EXISTS detection_events (
    id BIGSERIAL,
    event_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    severity TEXT NOT NULL DEFAULT 'high',
    event_type TEXT NOT NULL DEFAULT 'shoplifting.detected',
    trace_id TEXT,
    frame_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    detections JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    evidence_uri TEXT,
    t_capture BIGINT NOT NULL DEFAULT 0,
    t_output BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS event_id TEXT;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'high';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'shoplifting.detected';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS frame_ref JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS detections JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS detection_events_2026_03
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_04
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE INDEX IF NOT EXISTS idx_events_camera_id ON detection_events (camera_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON detection_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_trace_id ON detection_events (trace_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id ON detection_events (event_id);
