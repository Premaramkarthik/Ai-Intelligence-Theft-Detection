CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT,
    host TEXT,
    port INTEGER DEFAULT 554 CHECK (port > 0 AND port <= 65535),
    username TEXT,
    password TEXT,
    path TEXT,
    direct_rtsp_url TEXT,
    transport TEXT NOT NULL DEFAULT 'tcp' CHECK (transport IN ('tcp', 'udp')),
    status TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('active', 'inactive', 'error')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    last_validated_at TIMESTAMPTZ,
    last_validation_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        last_validation_status IN ('unknown', 'reachable', 'unreachable')
    ),
    last_validation_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT rtsp_source_check CHECK (
        direct_rtsp_url IS NOT NULL OR (host IS NOT NULL AND path IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_cameras_status ON cameras (status);
CREATE INDEX IF NOT EXISTS idx_cameras_created_at ON cameras (created_at DESC);
