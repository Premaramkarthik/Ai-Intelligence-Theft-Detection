SELECT *
FROM stream_state
WHERE ($1::text IS NULL OR camera_id = $1::text)
ORDER BY updated_at DESC;
