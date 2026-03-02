"""Prometheus metrics for Alerting service."""
from prometheus_client import Counter

METRICS_PORT = 9103

alerts_sent = Counter(
    "alerting_alerts_sent_total",
    "Total alerts successfully dispatched to consumers",
)
