"""
Utility functions for retry logic with exponential backoff.
"""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    retryable_exceptions: tuple = (Exception,),
    backoff_factor: float = 2.0,
):
    """
    Decorator for retry with exponential backoff.

    Args:
        max_retries: Max retry attempts (default from settings)
        base_delay: Initial delay in seconds (default from settings)
        max_delay: Max delay cap in seconds (default from settings)
        retryable_exceptions: Exceptions that trigger retry
        backoff_factor: Exponential backoff multiplier
    """
    settings = get_settings()
    max_retries = max_retries or settings.RETRY_MAX_ATTEMPTS
    base_delay = base_delay or settings.RETRY_BASE_DELAY
    max_delay = max_delay or settings.RETRY_MAX_DELAY

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (backoff_factor**attempt), max_delay)
                        logger.warning(
                            "[Retry] %s attempt %d/%d failed with %s: %s. Retrying in %.1fs...",
                            func.__name__,
                            attempt + 1,
                            max_retries,
                            type(e).__name__,
                            str(e)[:100],
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "[Retry] %s exhausted %d retries. Last error: %s",
                            func.__name__,
                            max_retries,
                            e,
                        )
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (backoff_factor**attempt), max_delay)
                        logger.warning(
                            "[Retry] %s attempt %d/%d failed with %s: %s. Retrying in %.1fs...",
                            func.__name__,
                            attempt + 1,
                            max_retries,
                            type(e).__name__,
                            str(e)[:100],
                            delay,
                        )
                        import time

                        time.sleep(delay)
                    else:
                        logger.error(
                            "[Retry] %s exhausted %d retries. Last error: %s",
                            func.__name__,
                            max_retries,
                            e,
                        )
            raise last_exception

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Shorthand for common retry scenarios
async_retry = lambda f: with_retry(
    retryable_exceptions=(ConnectionError, TimeoutError)
)(f)
sync_retry = lambda f: with_retry(retryable_exceptions=(ConnectionError, TimeoutError))(
    f
)
