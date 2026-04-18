WITH inserted AS (
    INSERT INTO cameras (
        id,
        name,
        location,
        host,
        port,
        username,
        password,
        path,
        direct_rtsp_url,
        transport,
        status,
        metadata,
        tags
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    RETURNING *
)
SELECT
    inserted.*,
    NULL::text AS stream_status,
    '{}'::jsonb AS stream_metadata
FROM inserted;
