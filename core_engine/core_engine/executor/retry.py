"""Configurable retry logic with exponential backoff and optional jitter.

Both synchronous and asynchronous callers are supported through separate
entry-points that share identical backoff semantics.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig(BaseModel):
    """Tuneable parameters for retry behaviour."""

    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts before re-raising.",
    )
    base_delay: float = Field(
        default=2.0,
        gt=0.0,
        description="Base delay in seconds for exponential backoff.",
    )
    max_delay: float = Field(
        default=60.0,
        gt=0.0,
        description="Upper bound on delay in seconds.",
    )
    jitter: bool = Field(
        default=True,
        description="When enabled, randomise the delay within [0.5x, 1.5x].",
    )


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """Return the backoff delay for *attempt* given *config*."""
    delay: float = min(config.base_delay * (2**attempt), config.max_delay)
    if config.jitter:
        delay *= random.uniform(0.5, 1.5)  # noqa: S311
    return delay


def retry_with_backoff(
    fn: Callable[[], T],
    config: RetryConfig,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute *fn* with synchronous retry and exponential backoff.

    Parameters
    ----------
    fn:
        A zero-argument callable to invoke.  On each retry the callable is
        invoked from scratch -- it must be safe to call repeatedly.
    config:
        Retry parameters (see :class:`RetryConfig`).
    retryable_exceptions:
        Only exceptions whose type appears in this tuple trigger a retry.
        All other exceptions propagate immediately.

    Returns
    -------
    T
        The return value of *fn* on the first successful call.

    Raises
    ------
    Exception
        The last exception raised by *fn* after all retry attempts are
        exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_retries:
                break
            delay = _compute_delay(attempt, config)
            logger.warning(
                "Retry %d/%d after %.1fs: %s",
                attempt + 1,
                config.max_retries,
                delay,
                exc,
            )
            time.sleep(delay)

    assert last_exception is not None  # noqa: S101
    raise last_exception


async def async_retry_with_backoff(
    fn: Callable[[], T],
    config: RetryConfig,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute *fn* with asynchronous retry and exponential backoff.

    Semantics are identical to :func:`retry_with_backoff` except that the
    inter-retry sleep is non-blocking (``asyncio.sleep``).

    Parameters
    ----------
    fn:
        A zero-argument callable (sync or async) to invoke.  If *fn* returns
        a coroutine it will be awaited.
    config:
        Retry parameters.
    retryable_exceptions:
        Exception types that trigger a retry.

    Returns
    -------
    T
        The return value of *fn* on success.
    """
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_retries:
                break
            delay = _compute_delay(attempt, config)
            logger.warning(
                "Retry %d/%d after %.1fs: %s",
                attempt + 1,
                config.max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    assert last_exception is not None  # noqa: S101
    raise last_exception
