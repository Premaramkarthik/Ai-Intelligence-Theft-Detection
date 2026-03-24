import logging

from src.utils.retry import calculate_backoff, log_retry_before_sleep


def test_calculate_backoff_uses_tenacity_exponential_wait() -> None:
    assert calculate_backoff(0, 4, 10) == 4
    assert calculate_backoff(1, 4, 10) == 4
    assert calculate_backoff(2, 4, 10) == 8
    assert calculate_backoff(4, 4, 10) == 10


def test_log_retry_before_sleep_emits_warning(caplog) -> None:
    logger = logging.getLogger("tests.retry")

    with caplog.at_level(logging.WARNING):
        delay = log_retry_before_sleep(
            logger,
            operation_name="camera_worker_reconnect[cam_1]",
            attempt=2,
            base_delay=4,
            max_delay=10,
            reason="Network connection lost!",
        )

    assert delay == 8
    assert (
        "Retrying camera_worker_reconnect[cam_1]: attempt 2 ended with: "
        "Network connection lost!. Sleeping 8.00s before the next attempt."
    ) in caplog.text
