# Observability

This backend exposes Prometheus metrics on a dedicated listener and includes a ready-to-run Prometheus + Grafana stack under `backend/docker-compose.yaml`.

## Metrics Endpoint

The FastAPI process starts a dedicated metrics HTTP listener with `prometheus_client.start_http_server(...)`.

Default endpoint:

```text
http://localhost:9109/metrics
```

Configuration lives in `src/core/config.py`:

- `METRICS_ENABLED`
- `METRICS_HOST`
- `METRICS_PORT`
- `METRICS_COLLECTION_INTERVAL_SECONDS`

## Local Stack

Start the observability services from the `backend/` directory:

```bash
docker compose up -d prometheus grafana
```

Then open:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Default Grafana credentials:

- username: `admin`
- password: `admin`

Override them with `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` in `backend/.env`.

## Provisioned Assets

- `observability/prometheus/prometheus.yml`
- `observability/prometheus/alerts.yml`
- `observability/grafana/provisioning/datasources/prometheus.yml`
- `observability/grafana/provisioning/dashboards/dashboards.yml`
- `observability/grafana/dashboards/opencv_pipeline.json`

Grafana provisions the Prometheus data source automatically and loads the dashboard into the `Pipeline Backend` folder.

## Scrape Targets

The provisioned Prometheus server scrapes:

- the backend metrics endpoint at `host.docker.internal:9109`
- Triton metrics at `triton:8002`
- Kafka JMX metrics at `kafka:7071`
- Prometheus itself at `prometheus:9090`

Because the backend usually runs on the host machine while Prometheus runs in Docker, `host.docker.internal` is used for the backend target.

## Dashboard Coverage

The provisioned Grafana dashboard includes:

- active cameras and worker health
- WebSocket connection count
- Triton connectivity
- decoded FPS by camera
- frame drop rate by camera
- p95 frame processing latency
- tracking active tracks
- inference queue depth
- inference request rate by model and strategy
- p95 inference execution latency
- API request rate
- CPU and memory usage
- dependency health

## Useful PromQL Queries

Decoded FPS by camera:

```promql
sum by (camera_id) (rate(stream_decoded_frames_total[1m]))
```

Frame drops by camera:

```promql
sum by (camera_id) (rate(frames_dropped_total[5m]))
```

P95 frame processing latency:

```promql
histogram_quantile(0.95, sum by (camera_id, le) (rate(frame_processing_latency_ms_bucket[5m])))
```

Inference request rate:

```promql
sum by (strategy, model_name, outcome) (rate(inference_requests_total[5m]))
```

P95 inference execution latency:

```promql
histogram_quantile(0.95, sum by (strategy, model_name, le) (rate(inference_execution_duration_seconds_bucket[5m])))
```

## Alerts

The bundled alert rules cover:

- backend metrics endpoint down
- Triton metrics endpoint down
- elevated frame drop rate
- elevated p95 frame processing latency
- inference queue backlog
- high backend RSS memory

These alerts are evaluated by Prometheus and appear in the Prometheus alerts UI even without an Alertmanager service.

## Notes

- Make sure the FastAPI backend is running before opening Grafana, otherwise the backend Prometheus target will show as down.
- The dashboard uses the actual metric names exposed by `src/observability/metrics.py`, not placeholder names.
- If you move the backend metrics endpoint off `9109`, update `observability/prometheus/prometheus.yml` to match.
