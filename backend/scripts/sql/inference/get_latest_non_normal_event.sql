SELECT
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
FROM inference_events
WHERE camera_id = $1
  AND label <> 'normal'
ORDER BY created_at DESC
LIMIT 1;
