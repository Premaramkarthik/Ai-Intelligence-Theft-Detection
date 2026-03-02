-- PostgreSQL schema for the detection events persistence layer.
-- Run once on DB initialisation: psql -U pipeline_user -d pipeline_events -f schema.sql

CREATE TABLE IF NOT EXISTS detection_events (
    id            BIGSERIAL,
    camera_id     TEXT        NOT NULL,
    class_name    TEXT        NOT NULL,
    confidence    REAL        NOT NULL,
    t_capture     BIGINT      NOT NULL,   -- perf_counter_ns at frame capture
    t_output      BIGINT      NOT NULL,   -- perf_counter_ns at inference output
    evidence_uri  TEXT,                   -- local path: /data/evidence/YYYY-MM/cam01/trace.jpg
    trace_id      TEXT,                   -- UUID for cross-service correlation
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Monthly partitions (create new ones at the start of each month)
CREATE TABLE IF NOT EXISTS detection_events_2026_02
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE IF NOT EXISTS detection_events_2026_03
    PARTITION OF detection_events
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- Indexes (per partition, PostgreSQL auto-propagates to child tables)
CREATE INDEX IF NOT EXISTS idx_events_camera_id  ON detection_events (camera_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON detection_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_trace_id   ON detection_events (trace_id);
