"""SQL/Model definitions for detection events."""
# In this asyncpg-based approach, we use raw SQL or a simple query builder.
# We'll define the table name and columns as constants.

TABLE_NAME = "detection_events"

INSERT_QUERY = """
INSERT INTO detection_events (
    event_id,
    organization_id,
    store_id,
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
    payload,
    evidence_uri,
    thumbnail_uri,
    review_status,
    review_note,
    model_version,
    config_version
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13::jsonb, $14, $15::jsonb, $16, $17, $18, $19, $20, $21)
"""
