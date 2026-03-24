INSERT INTO stream_state (
    camera_id,
    stream_id,
    status,
    desired_state,
    protocol,
    playback_path,
    playlist_path,
    metadata,
    last_event_at,
    updated_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
ON CONFLICT (camera_id) DO UPDATE
SET
    stream_id = EXCLUDED.stream_id,
    status = EXCLUDED.status,
    desired_state = EXCLUDED.desired_state,
    protocol = EXCLUDED.protocol,
    playback_path = EXCLUDED.playback_path,
    playlist_path = EXCLUDED.playlist_path,
    metadata = COALESCE(stream_state.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
    last_event_at = NOW(),
    updated_at = NOW()
RETURNING *;
