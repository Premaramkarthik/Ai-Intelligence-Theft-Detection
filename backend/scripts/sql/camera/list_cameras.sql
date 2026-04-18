SELECT
    c.*,
    COALESCE(s.status, 'stopped') AS stream_status,
    COALESCE(s.metadata, '{}'::jsonb) AS stream_metadata,
    COUNT(*) OVER() AS total_count
FROM cameras AS c
LEFT JOIN stream_state AS s
    ON s.camera_id = c.id
WHERE
    ($1::text IS NULL OR c.status = $1::text)
    AND (
        $2::text IS NULL
        OR c.id ILIKE '%' || $2 || '%'
        OR c.name ILIKE '%' || $2 || '%'
        OR COALESCE(c.location, '') ILIKE '%' || $2 || '%'
    )
ORDER BY c.created_at DESC
LIMIT $3 OFFSET $4;
