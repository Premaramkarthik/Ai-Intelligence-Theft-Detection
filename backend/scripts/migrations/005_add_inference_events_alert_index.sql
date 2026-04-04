CREATE INDEX IF NOT EXISTS idx_inference_events_camera_alerts_created_at
ON inference_events (camera_id, created_at DESC)
WHERE label <> 'normal';
