INSERT INTO inference_events (
    id,
    camera_id,
    track_id,
    persistent_id,
    label,
    confidence,
    "left",
    "top",
    width,
    height,
    model_name,
    created_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
RETURNING *;
