"""Prometheus metrics for Persistence service."""
from prometheus_client import Counter, Gauge, Histogram

METRICS_PORT = 9104

db_write_latency = Histogram(
    "persistence_db_write_latency_seconds",
    "Database insert latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)

db_writes_succeeded = Counter(
    "persistence_db_writes_succeeded_total",
    "Successful persistence writes",
)

db_writes_failed = Counter(
    "persistence_db_writes_failed_total",
    "Failed persistence writes",
)

redis_reconnects = Counter(
    "persistence_redis_reconnects_total",
    "Persistence Redis reconnect attempts",
)

persistence_ready = Gauge(
    "persistence_ready",
    "Persistence readiness flag",
)
