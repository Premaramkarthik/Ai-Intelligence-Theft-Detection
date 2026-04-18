SELECT
    c.*,
    COALESCE(s.status, 'stopped') AS stream_status,
    COALESCE(s.metadata, '{}'::jsonb) AS stream_metadata
FROM cameras AS c
LEFT JOIN stream_state AS s
    ON s.camera_id = c.id
WHERE c.id = $1;
