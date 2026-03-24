from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from tenacity import RetryAction, RetryCallState, Retrying, wait_exponential


class RetryPlanningError(RuntimeError):
    """Internal exception used to build a tenacity retry state for logging."""


def calculate_backoff(attempt: int, base_delay: float, max_delay: float) -> float:
    retry_state = _build_retry_state(
        attempt=attempt,
        base_delay=base_delay,
        max_delay=max_delay,
        reason="Retry scheduled.",
    )
    if retry_state.next_action is None:
        raise RuntimeError("Retry state does not have a next action configured.")
    return retry_state.next_action.sleep


def log_retry_before_sleep(
    logger: logging.Logger,
    *,
    operation_name: str,
    attempt: int,
    base_delay: float,
    max_delay: float,
    reason: str,
) -> float:
    retry_state = _build_retry_state(
        attempt=attempt,
        base_delay=base_delay,
        max_delay=max_delay,
        reason=reason,
    )
    _build_before_sleep_logger(logger, operation_name)(retry_state)
    if retry_state.next_action is None:
        raise RuntimeError("Retry state does not have a next action configured.")
    return retry_state.next_action.sleep


async def sleep_with_retry_logging(
    logger: logging.Logger,
    *,
    operation_name: str,
    attempt: int,
    base_delay: float,
    max_delay: float,
    reason: str,
) -> float:
    delay = log_retry_before_sleep(
        logger,
        operation_name=operation_name,
        attempt=attempt,
        base_delay=base_delay,
        max_delay=max_delay,
        reason=reason,
    )
    await asyncio.sleep(delay)
    return delay


def _build_retry_state(
    *,
    attempt: int,
    base_delay: float,
    max_delay: float,
    reason: str,
) -> RetryCallState:
    retrying = Retrying(
        wait=wait_exponential(
            multiplier=base_delay,
            min=base_delay,
            max=max_delay,
        )
    )
    retry_state = RetryCallState(retrying, None, (), {})
    retry_state.attempt_number = max(1, attempt)
    retry_state.set_exception((RetryPlanningError, RetryPlanningError(reason), None))
    delay = retrying.wait(retry_state)
    retry_state.next_action = RetryAction(delay)
    retry_state.idle_for = delay
    retry_state.upcoming_sleep = delay
    return retry_state


def _build_before_sleep_logger(
    logger: logging.Logger,
    operation_name: str,
) -> Callable[[RetryCallState], None]:
    def _log(retry_state: RetryCallState) -> None:
        if retry_state.outcome is None:
            raise RuntimeError("Retry log callback called before outcome was set.")
        if retry_state.next_action is None:
            raise RuntimeError("Retry log callback called before next action was set.")
        if retry_state.outcome.failed:
            outcome = retry_state.outcome.exception()
        else:
            outcome = retry_state.outcome.result()
        logger.warning(
            "Retrying %s: attempt %s ended with: %s. Sleeping %.2fs before the next attempt.",
            operation_name,
            retry_state.attempt_number,
            outcome,
            retry_state.next_action.sleep,
        )

    return _log
