CREATE TABLE IF NOT EXISTS inference_events (
    id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    persistent_id TEXT,
    label TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    "left" INTEGER NOT NULL,
    "top" INTEGER NOT NULL,
    width INTEGER NOT NULL CHECK (width >= 0),
    height INTEGER NOT NULL CHECK (height >= 0),
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inference_events_camera_created_at
ON inference_events (camera_id, created_at DESC);
