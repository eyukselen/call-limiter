import time
import threading
from functools import wraps
from typing import Callable, Tuple, Type, Optional, Any


class CallLimiter:
    """
    High-Performance Rate Limiter.

    Modes
    -----
    allow_burst=True
        Fixed-window burst limiter.
        Example:
            calls=5, period=10

        Allows:
            5 immediate calls
            then blocks until next 10-second window.

    allow_burst=False
        Strict drip/paced limiter.
        Evenly spaces calls across the period.

    Features
    --------
    - Thread-safe
    - High-precision sleep
    - Adaptive OS jitter compensation
    - CPU efficient (minimal spin waiting)
    """

    def __init__(
            self,
            calls: int,
            period: float = 1.0,
            allow_burst: bool = False,
    ):
        if calls <= 0:
            raise ValueError("calls must be positive")

        if period <= 0:
            raise ValueError("period must be positive")

        self.calls = calls
        self.period = period
        self.allow_burst = allow_burst

        self.period_per_call = period / calls

        self.lock = threading.Lock()

        now = time.perf_counter()

        if allow_burst:
            # FIXED WINDOW MODE
            self.capacity = calls
            self.calls_in_window = 0
            self.window_start = now

        else:
            # DRIP MODE
            self.next_allowed_time = now

        # Adaptive sleep jitter learning
        self.os_jitter = 0.0
        self.samples_collected = 0
        self.max_samples = 50

    def _learn_jitter(self, requested_sleep: float, actual_sleep: float):
        """
        Learn average OS sleep overshoot.
        """
        overshoot = max(0.0, actual_sleep - requested_sleep)

        with self.lock:
            self.samples_collected += 1

            alpha = 1.0 / min(self.samples_collected, self.max_samples)

            self.os_jitter = (
                                     self.os_jitter * (1.0 - alpha)
                             ) + (overshoot * alpha)

            # Cap insane scheduler spikes
            self.os_jitter = min(self.os_jitter, 0.2)

    def _sleep_precise(self, duration: float):
        """
        High precision sleep with adaptive jitter compensation.

        Strategy:
            1. Coarse sleep
            2. Fine sleep stages
            3. Tiny final spin
        """
        if duration <= 0:
            return

        start = time.perf_counter()
        target = start + duration

        # Snapshot jitter stats
        with self.lock:
            jitter = self.os_jitter
            samples = self.samples_collected

        # Conservative early learning
        if samples < 3:
            safety_margin = duration * 0.6
        else:
            safety_margin = max(jitter, duration * 0.05)

        coarse_sleep = duration - safety_margin

        if coarse_sleep > 0:
            before = time.perf_counter()

            time.sleep(coarse_sleep)

            actual = time.perf_counter() - before

            self._learn_jitter(coarse_sleep, actual)

        fine_intervals = (
            0.001,
            0.0001,
            0.00001,
        )

        for interval in fine_intervals:
            while True:
                remaining = target - time.perf_counter()

                if remaining <= interval:
                    break

                time.sleep(interval)

        while time.perf_counter() < target:
            pass

    def wait(self):
        """
        Block until a call is allowed.
        """
        if self.allow_burst:

            while True:

                with self.lock:

                    now = time.perf_counter()

                    elapsed = now - self.window_start

                    # Advance windows precisely
                    if elapsed >= self.period:
                        windows_passed = int(elapsed / self.period)

                        self.window_start += (
                                windows_passed * self.period
                        )

                        self.calls_in_window = 0

                    # Still capacity left in this window
                    if self.calls_in_window < self.capacity:
                        self.calls_in_window += 1
                        return

                    # Window exhausted
                    wait_time = self.period - (
                            now - self.window_start
                    )

                self._sleep_precise(wait_time)

        else:
            now = time.perf_counter()
            with self.lock:
                # Catch up if we are behind schedule
                if now > self.next_allowed_time:
                    self.next_allowed_time = now

                scheduled_time = self.next_allowed_time

                # Reserve next slot
                self.next_allowed_time += self.period_per_call

            wait_time = scheduled_time - now

            if wait_time > 0:
                self._sleep_precise(wait_time)

    def __call__(self, func: Callable) -> Callable:

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