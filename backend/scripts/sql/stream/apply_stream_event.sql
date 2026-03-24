INSERT INTO stream_state (
    camera_id,
    stream_id,
    status,
    desired_state,
    protocol,
    playback_path,
    playlist_path,
    worker_pid,
    worker_started_at,
    last_event_at,
    last_heartbeat_at,
    last_error_code,
    last_error_message,
    restart_count,
    reconnect_attempts,
    metadata,
    updated_at
)
VALUES (
    $1,
    $2,
    $3,
    $4,
    $5,
    $6,
    $7,
    $8,
    CASE WHEN $3 = 'running' THEN $9 ELSE NULL END,
    $9,
    CASE WHEN $3 = 'running' THEN $9 ELSE NULL END,
    $10,
    $11,
    $12,
    $13,
    $14,
    NOW()
)
ON CONFLICT (camera_id) DO UPDATE
SET
    stream_id = EXCLUDED.stream_id,
    status = EXCLUDED.status,
    desired_state = EXCLUDED.desired_state,
    protocol = EXCLUDED.protocol,
    playback_path = COALESCE(EXCLUDED.playback_path, stream_state.playback_path),
    playlist_path = COALESCE(EXCLUDED.playlist_path, stream_state.playlist_path),
    worker_pid = EXCLUDED.worker_pid,
    worker_started_at = CASE
        WHEN EXCLUDED.status = 'running'
            AND (
                stream_state.worker_started_at IS NULL
                OR stream_state.worker_pid IS DISTINCT FROM EXCLUDED.worker_pid
            )
            THEN EXCLUDED.last_event_at
        ELSE stream_state.worker_started_at
    END,
    last_event_at = EXCLUDED.last_event_at,
    last_heartbeat_at = CASE
        WHEN EXCLUDED.status = 'running' THEN EXCLUDED.last_event_at
        ELSE stream_state.last_heartbeat_at
    END,
    last_error_code = EXCLUDED.last_error_code,
    last_error_message = EXCLUDED.last_error_message,
    restart_count = GREATEST(stream_state.restart_count, EXCLUDED.restart_count),
    reconnect_attempts = EXCLUDED.reconnect_attempts,
    metadata = COALESCE(stream_state.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
    updated_at = NOW()
RETURNING *;
