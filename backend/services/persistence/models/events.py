"""SQL/Model definitions for detection events."""
# In this asyncpg-based approach, we use raw SQL or a simple query builder.
# We'll define the table name and columns as constants.

TABLE_NAME = "detection_events"

INSERT_QUERY = """
INSERT INTO detection_events (
    event_id,
    camera_id,
    trace_id,
    event_type,
    class_name,
    confidence,
    severity,
    created_at,
    frame_ref,
    detections,
    metadata,
    schema_version,
    payload
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11::jsonb, $12, $13::jsonb)
"""
