# Phase 5 Runbook

## What Changed

- Inference now schedules work from per-camera queues with fair polling.
- Live video previews use MJPEG over HTTP, while overlays/incident metadata stay on WebSocket.
- Incidents can persist evidence paths, review status, and store scope.
- Review status updates are available through `PATCH /api/events/{event_id}/review`.

## Deploy Notes

1. Run schema migrations from `scripts/schema.sql` before starting services.
2. Mount `evidence-data` to both `signaling` and `inference`.
3. If enabling ReID, set:
   - `REID_ENABLED=true`
   - `REID_BACKEND=pgvector`
   - ensure pgvector is installed in PostgreSQL

## Rollback Notes

1. Revert application deploy.
2. Keep new schema columns in place; the previous application version ignores them.
3. If MJPEG rollback is required, restore the previous WebSocket image path in the frontend and signaling camera stream route together.
