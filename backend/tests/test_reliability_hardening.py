from __future__ import annotations

from uuid import UUID

from shared.runtime.health_server import RuntimeState
from shared.runtime.retry import next_backoff_delay
from shared.tracing import new_trace_id


def test_runtime_state_reports_ready_dependencies():
    state = RuntimeState(service_name="inference")
    state.set_booted(True)
    state.dependency("redis", True, "connected")
    state.update_detail(detector_loaded=True, classifier_loaded=True)
    state.set_ready(True)

    payload = state.readiness_payload()

    assert payload["status"] == "ready"
    assert payload["dependencies"]["redis"]["ok"] is True
    assert payload["details"]["detector_loaded"] is True


def test_runtime_state_reports_degraded_truthfully():
    state = RuntimeState(service_name="persistence")
    state.set_booted(True)
    state.dependency("postgres", False, "connection refused")
    state.set_degraded(True)

    payload = state.readiness_payload()

    assert payload["status"] == "degraded"
    assert payload["ready"] is False
    assert payload["dependencies"]["postgres"]["detail"] == "connection refused"


def test_next_backoff_delay_caps_growth():
    assert next_backoff_delay(0) == 1.0
    assert next_backoff_delay(1) == 1.0
    assert next_backoff_delay(2) == 2.0
    assert next_backoff_delay(10, cap=8.0) == 8.0


def test_new_trace_id_is_full_uuid():
    trace_id = new_trace_id()

    assert len(trace_id) == 36
    assert str(UUID(trace_id)) == trace_id
