# Persistence Service: Reliable Event Logging

The **Persistence Service** is responsible for the long-term storage of detection data. It ensures that every important interaction and shoplifting event is safely recorded in the PostgreSQL database for later auditing and retrieval.

---

## 1. Reliable Queue Pattern

The system uses a **Reliable Producer-Consumer** pattern via Redis:
1.  The `Inference` service pushes serialized `DetectionEvent` objects into a Redis list called `persistence_queue`.
2.  The `Persistence` service continuously "blocks" on this queue (`BRPOP`), ensuring no events are missed even during database maintenance or high-load spikes.

---

## 2. Core Operations

- **Database Normalization**: Maps asynchronous Redis payloads into the structured SQL schema in PostgreSQL.
- **Batching**: To improve performance, the service can be configured to perform batch inserts, reducing the number of round-trips to the database.
- **Evidence Management**: (Future) Responsible for taking relevant frame snapshots from SHM and saving them to disk/S3 as JPEG evidence.

---

## 3. Technology Stack

- **PostgreSQL**: Industry-standard relational database for high-integrity event logs.
- **Asyncpg**: Extremely fast, asynchronous PostgreSQL client library.
- **Redis Streams/Lists**: Used as the temporary buffer to decouple AI processing from Database writing.

---

## 4. Database Schema Overview

The service interacts with the following primary tables (defined in `scripts/schema.sql`):
- **`events`**: The core log table recording `camera_id`, `label`, `confidence`, and `timestamp`.
- **`sessions`**: (Future) Records of prolonged person presence in the store.

---

## 🛠️ Operational Commands

### Checking Database Health
You can verify that persistence is working by checking the row counts in the database:
```bash
docker exec -it pipeline_opencv-postgres-1 psql -U pipeline_user -d pipeline_events -c "SELECT count(*) FROM events;"
```
