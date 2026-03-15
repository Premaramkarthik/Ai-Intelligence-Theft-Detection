"""Prometheus metrics for Alerting service."""
from prometheus_client import Counter, Gauge

METRICS_PORT = 9103

alerts_sent = Counter(
    "alerting_alerts_sent_total",
    "Total alerts successfully dispatched to consumers",
)

alerts_failed = Counter(
    "alerting_alerts_failed_total",
    "Alert delivery failures",
)

redis_reconnects = Counter(
    "alerting_redis_reconnects_total",
    "Alerting Redis reconnect attempts",
)

alerting_ready = Gauge(
    "alerting_ready",
    "Alerting readiness flag",
)
