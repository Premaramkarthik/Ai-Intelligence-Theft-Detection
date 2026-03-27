# Observability

This backend exposes Prometheus metrics on a dedicated listener and ships Grafana-ready provisioning for dashboards and alert rules.

## Metrics Endpoint

The backend starts a dedicated Prometheus HTTP endpoint with `prometheus_client.start_http_server(...)`.

Default endpoint:

```text
http://localhost:9109/metrics
```

Configuration lives in `src/core/config.py`:

- `METRICS_ENABLED`
- `METRICS_HOST`
- `METRICS_PORT`
- `METRICS_COLLECTION_INTERVAL_SECONDS`

## Application Metrics

- `frames_received_total{camera_id="..."}`
- `frames_dropped_total{camera_id="..."}`
- `frame_processing_latency_ms_bucket{camera_id="..."}`
- `queue_size`

## System Metrics

- `system_cpu_usage_percent`
- `process_cpu_usage_percent`
- `system_memory_usage_bytes`
- `process_memory_usage_bytes`
- `system_network_receive_bytes_total`
- `system_network_transmit_bytes_total`

## Prometheus Setup

Use:

- [prometheus.yml.tmpl](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus/prometheus.yml.tmpl)
- [alerts.yml](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus/alerts.yml)

The local setup now uses a cross-platform Prometheus target template. By default it scrapes `host.docker.internal:9109`, which works on Docker Desktop for Windows and macOS, and Docker Compose adds a `host-gateway` mapping on Linux. The `5s` scrape interval is a reasonable default for live worker and queue visibility without excessive overhead.

If your environment needs a different host target, set:

```bash
export PROMETHEUS_SCRAPE_TARGET=YOUR_HOST_OR_IP:9109
```

before `docker compose up`.

## Grafana Setup

Provisioning files:

- [prometheus.yml](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/provisioning/datasources/prometheus.yml)
- [dashboards.yml](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/provisioning/dashboards/dashboards.yml)
- [realtime_video_pipeline.json](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/dashboards/realtime_video_pipeline.json)

Manual Grafana flow:

1. Add a Prometheus data source pointed at `http://prometheus:9090`.
1. Add a Prometheus data source pointed at `http://prometheus:9090`.
2. Import `observability/grafana/dashboards/realtime_video_pipeline.json`.
3. Save the dashboard in a shared folder.

## PromQL Queries

FPS:

```promql
rate(frames_received_total[1m])
```

Frame drops:

```promql
rate(frames_dropped_total[1m])
```

Latency:

```promql
histogram_quantile(0.95, rate(frame_processing_latency_ms_bucket[1m]))
```

CPU:

```promql
system_cpu_usage_percent
```

Memory:

```promql
process_memory_usage_bytes
```

Process CPU:

```promql
process_cpu_usage_percent
```

Queue size:

```promql
queue_size
```

## Alerts

The provided alerts cover:

- high CPU usage
- rapid RSS growth
- high frame drop rate
- high p95 frame processing latency

## Official References

- https://prometheus.io/docs/instrumenting/clientlibs/
- https://prometheus.io/docs/practices/histograms/
- https://prometheus.io/docs/visualization/grafana/
- https://grafana.com/docs/grafana/latest/datasources/prometheus/
- https://grafana.com/docs/grafana/latest/dashboards/
