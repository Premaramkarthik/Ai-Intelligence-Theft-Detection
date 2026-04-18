WITH updated AS (
    UPDATE cameras
    SET
        name = $2,
        location = $3,
        host = $4,
        port = $5,
        username = $6,
        password = $7,
        path = $8,
        direct_rtsp_url = $9,
        transport = $10,
        status = $11,
        metadata = $12,
        tags = $13,
        updated_at = NOW()
    WHERE id = $1
    RETURNING *
)
SELECT
    updated.*,
    COALESCE(s.status, 'stopped') AS stream_status,
    COALESCE(s.metadata, '{}'::jsonb) AS stream_metadata
FROM updated
LEFT JOIN stream_state AS s
    ON s.camera_id = updated.id;
