-- Drop old inference_events table (schema incompatible with current event_repository)
DROP INDEX IF EXISTS idx_inference_events_camera_alerts_created_at;
DROP INDEX IF EXISTS idx_inference_events_camera_created_at;
DROP TABLE IF EXISTS inference_events;

-- Recreate with schema matching InferenceEventRepository._INSERT
CREATE TABLE inference_events (
    id          BIGSERIAL PRIMARY KEY,
    camera_id   TEXT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    stream_name TEXT NOT NULL,
    persistent_id TEXT NOT NULL,
    local_track_id TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    score       DOUBLE PRECISION NOT NULL CHECK (score >= 0.0 AND score <= 1.0),
    alert_level TEXT NOT NULL,
    label       TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    sampled_at  TIMESTAMPTZ NOT NULL,
    emitted_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_inference_events_camera_emitted_at
    ON inference_events (camera_id, emitted_at DESC);

CREATE INDEX idx_inference_events_alert_level
    ON inference_events (camera_id, emitted_at DESC)
    WHERE alert_level <> 'normal';
