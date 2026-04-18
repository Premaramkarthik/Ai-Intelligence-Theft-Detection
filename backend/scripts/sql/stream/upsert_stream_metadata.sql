INSERT INTO stream_state (
    camera_id,
    stream_id,
    status,
    desired_state,
    protocol,
    metadata,
    last_event_at,
    updated_at
)
VALUES (
    $1,
    $1,
    'stopped',
    'stopped',
    'webrtc',
    $2::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (camera_id) DO UPDATE
SET
    metadata = COALESCE(stream_state.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
    last_event_at = NOW(),
    updated_at = NOW()
RETURNING *;
