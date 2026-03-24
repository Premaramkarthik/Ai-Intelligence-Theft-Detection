UPDATE stream_state
SET
    status = $2,
    desired_state = $3,
    metadata = COALESCE(metadata, '{}'::jsonb) || COALESCE($4::jsonb, '{}'::jsonb),
    last_event_at = NOW(),
    updated_at = NOW()
WHERE camera_id = $1
RETURNING *;
