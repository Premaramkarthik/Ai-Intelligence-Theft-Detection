"""SQL/Model definitions for detection events."""
# In this asyncpg-based approach, we use raw SQL or a simple query builder.
# We'll define the table name and columns as constants.

TABLE_NAME = "detection_events"

INSERT_QUERY = """
INSERT INTO detection_events (camera_id, trace_id, label, confidence, evidence_path, created_at)
VALUES ($1, $2, $3, $4, $5, $6)
"""
