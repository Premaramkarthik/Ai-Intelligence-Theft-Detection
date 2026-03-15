CREATE TABLE IF NOT EXISTS detection_events (
    id BIGSERIAL,
    event_id TEXT NOT NULL,
    organization_id TEXT NOT NULL DEFAULT 'default-org',
    store_id TEXT NOT NULL DEFAULT 'main-store',
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
    thumbnail_uri TEXT,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    review_note TEXT,
    model_version TEXT,
    config_version TEXT,
    t_capture BIGINT NOT NULL DEFAULT 0,
    t_output BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS event_id TEXT;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'high';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'shoplifting.detected';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'default-org';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS store_id TEXT NOT NULL DEFAULT 'main-store';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS frame_ref JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS detections JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS thumbnail_uri TEXT;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'unreviewed';
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS review_note TEXT;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE detection_events ADD COLUMN IF NOT EXISTS config_version TEXT;

CREATE TABLE IF NOT EXISTS detection_events_2026_03
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_04
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_05
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_06
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_07
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_08
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_09
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_10
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_11
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_12
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS detection_events_2027_01
    PARTITION OF detection_events
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');

CREATE TABLE IF NOT EXISTS detection_events_2027_02
    PARTITION OF detection_events
    FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');

CREATE TABLE IF NOT EXISTS detection_events_2027_03
    PARTITION OF detection_events
    FOR VALUES FROM ('2027-03-01') TO ('2027-04-01');

CREATE INDEX IF NOT EXISTS idx_events_camera_id ON detection_events (camera_id);
CREATE INDEX IF NOT EXISTS idx_events_store_id ON detection_events (store_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON detection_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_trace_id ON detection_events (trace_id);
DROP INDEX IF EXISTS idx_events_event_id;
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id_created_at
    ON detection_events (event_id, created_at);

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
    WHEN undefined_file THEN
        RAISE NOTICE 'pgvector extension unavailable; ReID index skipped';
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        EXECUTE '
            CREATE TABLE IF NOT EXISTS reid_identities (
                global_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL DEFAULT ''default-org'',
                store_id TEXT NOT NULL DEFAULT ''main-store'',
                embedding vector(576) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )';
    END IF;
END $$;
