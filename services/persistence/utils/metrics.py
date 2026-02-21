"""Prometheus metrics for Persistence service."""
from prometheus_client import Histogram

METRICS_PORT = 9104

db_write_latency = Histogram(
    "persistence_db_write_latency_seconds",
    "Database insert latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)
