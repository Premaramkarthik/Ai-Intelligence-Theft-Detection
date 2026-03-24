CREATE TABLE IF NOT EXISTS stream_state (
    camera_id TEXT PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    stream_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('stopped', 'starting', 'running', 'stopping', 'reconnecting', 'error', 'crashed')
    ),
    desired_state TEXT NOT NULL DEFAULT 'stopped' CHECK (desired_state IN ('running', 'stopped')),
    protocol TEXT NOT NULL DEFAULT 'hls' CHECK (protocol IN ('hls')),
    playback_path TEXT,
    playlist_path TEXT,
    worker_pid INTEGER,
    worker_started_at TIMESTAMPTZ,
    last_event_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_message TEXT,
    restart_count INTEGER NOT NULL DEFAULT 0,
    reconnect_attempts INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stream_state_status ON stream_state (status);
CREATE INDEX IF NOT EXISTS idx_stream_state_updated_at ON stream_state (updated_at DESC);
