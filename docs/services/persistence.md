# Persistence Service

The **Persistence Service** ensures that all detection data is recorded for long-term storage, auditing, and retraining.

## Purpose
- Buffer and write detection events to the relational database.
- Save "evidence" images/videos of suspicious events to persistent storage.
- Manage data retention and pruning.

## Technologies Used
- **PostgreSQL**: The primary relational database for structured event data.
- **Asyncpg**: A high-performance, asynchronous PostgreSQL client library for Python.
- **Aiofiles**: Used for non-blocking file I/O when saving evidence images to the filesystem.
- **SQLAlchemy (Core)**: Used for robust SQL expression building (optional, often alongside asyncpg).

## Operations
- **Automatic Initialization**: On startup, it checks the database schema and executes `scripts/schema.sql` if tables are missing.
- **Batched Inserts**: To minimize DB load, it collects events over a short window (`PERSISTENCE_BATCH_WINDOW_MS`) and performs a bulk insert.
- **Evidence Archiving**: When a shoplifting event is confirmed, it extracts the relevant frames from SHM and saves them as JPEGs in `EVIDENCE_STORAGE_PATH`.
- **Pruning**: Automatically deletes records and files older than `EVIDENCE_RETENTION_DAYS`.

## Schema Highlights
- `events`: Individual detections (timestamp, camera_id, track_id, class_id, confidence).
- `alerts`: Records of dispatched notifications.
- `cameras`: Status and configuration history of each source.
