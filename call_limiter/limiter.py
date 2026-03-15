import time
import threading
from functools import wraps
from typing import Callable, Tuple, Type, Optional, Any


class CallLimiter:
    def __init__(self, calls: int, period: float = 1.0, allow_burst: bool = False):
        self.rate = calls / period
        self.capacity = float(calls) if allow_burst else 1.0
        self.tokens = self.capacity
        self.last_refill = time.perf_counter()
        self.lock = threading.Lock()

        # Hardware Calibration
        t0 = time.perf_counter()
        _ = time.perf_counter()
        self.pulse = time.perf_counter() - t0
        self.os_jitter = 0.0

    def wait(self):
        with self.lock:
            now = time.perf_counter()

            # If the period has passed, reset the bucket and the window
            if now - self.last_refill >= (1.0 / self.rate * self.capacity):  # Total period
                self.tokens = self.capacity
                self.last_refill = now

            if self.tokens < 1.0:
                # Calculate time remaining in the current window
                sleep_needed = (self.last_refill + (self.capacity / self.rate)) - now

                if sleep_needed > 0:
                    # --- High Precision Sleep ---
                    if sleep_needed > self.os_jitter:
                        t_before = time.perf_counter()
                        time.sleep(max(0, sleep_needed - self.os_jitter))
                        self.os_jitter = max(self.os_jitter, (time.perf_counter() - t_before) - sleep_needed)

                    target = now + sleep_needed
                    while time.perf_counter() < target:
                        pass

                # After waiting, the window resets
                self.tokens = self.capacity
                self.last_refill = time.perf_counter()

            self.tokens -= 1.0

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper


class CallRetry:
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


import functools
from typing import Callable, Optional, Any, Tuple, Type


class ResilientLimiter:
    def __init__(
            self,
            calls: int,
            period: float = 1.0,
            allow_burst: bool = False,
            retry_count: int = 3,
            retry_interval: float = 1.0,
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
        # We wrap the function with Retry first, then Limiter.
        # This ensures every individual attempt (including retries)
        # is intercepted by the limiter's wait() logic.
        @self.limiter
        @self.retry
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper