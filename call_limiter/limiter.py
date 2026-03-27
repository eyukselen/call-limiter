import time
import threading
from functools import wraps
from typing import Callable, Tuple, Type, Optional, Any


class CallLimiter:
    """A high-precision, thread-safe rate limiter using a token bucket algorithm.

    Paces function calls to stay within a specified rate limit. Supports two
    modes: burst (all calls fire immediately up to capacity) and drip (calls
    are evenly spaced across the period).

    Uses a hybrid sleep strategy combining ``time.sleep()`` with a busy-wait
    loop for sub-millisecond precision. OS scheduling jitter is learned
    automatically via an adaptive moving average during runtime.

    Can be used as a decorator or by calling ``wait()`` directly.

    Args:
        calls: Maximum number of calls allowed per period.
        period: Time window in seconds for the rate limit.
        allow_burst: If True, all calls in a period can fire immediately.
            If False, calls are evenly spaced (drip mode).

    Examples:
        As a decorator with burst mode:

        >>> limiter = CallLimiter(calls=5, period=1.0, allow_burst=True)
        >>> @limiter
        ... def my_function():
        ...     pass

        As a decorator with drip mode (one call every 0.2s):

        >>> limiter = CallLimiter(calls=5, period=1.0, allow_burst=False)
        >>> throttled = limiter(my_function)

        Direct usage with ``wait()``:

        >>> limiter = CallLimiter(calls=10, period=1.0)
        >>> for _ in range(10):
        ...     limiter.wait()
        ...     do_work()
    """

    def __init__(self, calls: int, period: float = 1.0, allow_burst: bool = False):
        self.rate = calls / period
        self.capacity = float(calls) if allow_burst else 1.0
        self.window = self.capacity / self.rate
        self.tokens = self.capacity
        self.last_refill = time.perf_counter()
        self.lock = threading.Lock()

        self.os_jitter = 0.0
        self.samples_collected = 0

    def wait(self):
        """Block until a token is available, enforcing the configured rate limit.

        Acquires a token from the bucket, sleeping if necessary to maintain
        the target rate. Uses high-precision timing with adaptive jitter
        compensation to minimize drift.

        This method is thread-safe.
        """
        with self.lock:
            now = time.perf_counter()

            # If the period has passed, reset the bucket and the window
            if now - self.last_refill >= self.window:
                self.tokens = self.capacity
                self.last_refill = now

            if self.tokens < 1.0:
                # Calculate time remaining in the current window
                sleep_needed = (self.last_refill + self.window) - now

                if sleep_needed > 0:
                    # --- High Precision Sleep ---
                    # Use a safety margin to always undershoot time.sleep().
                    # The busy-wait loop corrects forward to the exact target.
                    # This prevents overshoot on high-jitter systems (e.g. macOS)
                    # where time.sleep() can exceed the requested duration.
                    safety_margin = max(self.os_jitter, sleep_needed * 0.2)
                    coarse = sleep_needed - safety_margin

                    if coarse > 0:
                        t_before = time.perf_counter()
                        time.sleep(coarse)
                        actual_sleep = time.perf_counter() - t_before

                        # Learn OS jitter via adaptive EMA
                        measured_jitter = max(0, actual_sleep - coarse)
                        self.samples_collected += 1
                        alpha = 1.0 / min(20, self.samples_collected)
                        self.os_jitter = min(0.1, (self.os_jitter * (1 - alpha)) + (measured_jitter * alpha))

                    target = now + sleep_needed
                    while time.perf_counter() < target:
                        pass

                # After waiting, the window resets
                self.tokens = self.capacity
                # Fix: Update last_refill relative to target time to avoid drift
                self.last_refill = now + sleep_needed if sleep_needed > 0 else now

            self.tokens -= 1.0

    def __call__(self, func):
        """Decorate a function to enforce the rate limit before each call.

        Args:
            func: The function to wrap with rate limiting.

        Returns:
            A wrapped function that calls ``wait()`` before each invocation.
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper


class CallRetry:
    """A configurable retry decorator for resilient function execution.

    Wraps a function to automatically retry on specified exceptions, with
    a fixed delay between attempts. Supports optional logging on each retry
    and a fallback function when all retries are exhausted.

    Can be used as a decorator or called directly to wrap a function.

    Args:
        retry_count: Maximum number of retries after the initial attempt.
            Total attempts will be ``retry_count + 1``.
        retry_interval: Delay in seconds between retry attempts.
        retry_exceptions: Tuple of exception types that trigger a retry.
            Any exception not in this tuple will propagate immediately.
        on_retry: Optional callback invoked on each retry. Receives the
            caught exception and the current attempt number (1-indexed).
        fallback: Optional function called when all retries are exhausted.
            Receives the last exception, and its return value is used as the
            overall result. If not provided, the last exception is raised.

    Examples:
        Basic retry with fallback:

        >>> retry = CallRetry(
        ...     retry_count=3,
        ...     retry_interval=1.0,
        ...     retry_exceptions=(ValueError,),
        ...     on_retry=lambda e, n: print(f"Retry {n}: {e}"),
        ...     fallback=lambda e: "default"
        ... )
        >>> resilient_func = retry(my_function)

        Retry without fallback (raises on exhaustion):

        >>> retry = CallRetry(retry_count=5, retry_interval=0.5)
        >>> resilient_func = retry(my_function)
    """

    def __init__(
            self,
            retry_count: int = 5,
            retry_interval: float = 1.0,
            retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
            on_retry: Optional[Callable[[Exception, int], None]] = None,
            fallback: Optional[Callable[[Exception], Any]] = None
    ):
        self.retry_count = retry_count
        self.retry_interval = retry_interval
        self.retry_exceptions = retry_exceptions
        self.on_retry = on_retry
        self.fallback = fallback

    def __call__(self, func: Callable) -> Callable:
        """Decorate a function to apply retry logic on each call.

        Args:
            func: The function to wrap with retry logic.

        Returns:
            A wrapped function that retries on configured exceptions.
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            # 0 to retry_count means (retry_count + 1) total attempts
            for attempt in range(1, self.retry_count + 2):
                try:
                    return func(*args, **kwargs)

                except self.retry_exceptions as e:
                    last_exception = e

                    # Check if we have attempts left
                    if attempt <= self.retry_count:
                        # Observability: Fire the logger if provided
                        if self.on_retry:
                            self.on_retry(e, attempt)

                        time.sleep(self.retry_interval)
                        continue

                    # If we reach here, we've exhausted retries
                    if self.fallback:
                        return self.fallback(e)

                    raise last_exception

        return wrapper


class ResilientLimiter:
    """A rate limiter with built-in retry logic for resilient function execution.

    Combines ``CallLimiter`` and ``CallRetry`` so that every call — including
    retries — respects the configured rate limit. This prevents retry storms
    from overwhelming a rate-limited service.

    Args:
        calls: Maximum number of calls allowed per period.
        period: Time window in seconds for the rate limit.
        allow_burst: If True, calls can fire immediately up to capacity.
            If False, calls are evenly spaced (drip mode).
        retry_count: Maximum number of retries after the initial attempt.
        retry_interval: Extra delay in seconds between retry attempts,
            added on top of the rate limiter's pacing. Defaults to 0
            because the rate limiter already enforces pacing.
        retry_exceptions: Tuple of exception types that trigger a retry.
        on_retry: Optional callback invoked on each retry. Receives the
            caught exception and the current attempt number (1-indexed).
            If not provided, retries happen silently.
        fallback: Optional function called when all retries are exhausted.
            Receives the last exception, and its return value is used as
            the overall result. If not provided, the last exception is raised.

    Examples:
        Rate-limited function with retry and fallback:

        >>> limiter = ResilientLimiter(
        ...     calls=5,
        ...     period=1.0,
        ...     allow_burst=True,
        ...     retry_count=3,
        ...     on_retry=lambda e, n: print(f"Retry {n}: {e}"),
        ...     fallback=lambda e: "default"
        ... )
        >>> @limiter
        ... def my_function():
        ...     pass
    """

    def __init__(
            self,
            calls: int,
            period: float = 1.0,
            allow_burst: bool = False,
            retry_count: int = 3,
            retry_interval: float = 0,
            retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
            on_retry: Optional[Callable[[Exception, int], None]] = None,
            fallback: Optional[Callable[[Exception], Any]] = None
    ):
        # 1. Initialize the Rate Limiter (The Pace)
        self.limiter = CallLimiter(
            calls=calls,
            period=period,
            allow_burst=allow_burst
        )

        # 2. Initialize the Retry Logic (The Resilience)
        self.retry = CallRetry(
            retry_count=retry_count,
            retry_interval=retry_interval,
            retry_exceptions=retry_exceptions,
            on_retry=on_retry,
            fallback=fallback
        )

    def __call__(self, func: Callable) -> Callable:
        """Decorate a function with rate limiting and retry logic.

        Args:
            func: The function to wrap. Each call and retry will respect
                the configured rate limit.

        Returns:
            A wrapped function with both rate limiting and retry behavior.
        """
        @self.retry
        @self.limiter
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper