WITH updated AS (
    UPDATE cameras
    SET
        last_validated_at = NOW(),
        last_validation_status = $2,
        last_validation_message = $3,
        updated_at = NOW()
    WHERE id = $1
    RETURNING *
)
SELECT updated.*, COALESCE(s.status, 'stopped') AS stream_status
FROM updated
LEFT JOIN stream_state AS s
    ON s.camera_id = updated.id;
