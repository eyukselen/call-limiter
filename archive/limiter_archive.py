import threading
import time
from functools import wraps
from typing import Callable


# original CallLimiter in limiter.py as of v1.0.4
# CallLimiterV1
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
                    #
                    # Before enough jitter samples are collected, use a large
                    # percentage-based margin (60%) so the busy-wait handles
                    # most of the wait. Once os_jitter has learned the real
                    # platform jitter, switch to using it directly.
                    if self.samples_collected < 3:
                        safety_margin = sleep_needed * 0.6
                    else:
                        safety_margin = max(self.os_jitter, sleep_needed * 0.1)
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


class CallLimiterV2:
    def __init__(self, calls: int, period: float = 1.0, allow_burst: bool = False):
        self.rate = calls / period
        self.capacity = float(calls) if allow_burst else 1.0
        self.window = self.capacity / self.rate
        self.tokens = self.capacity
        self.last_refill = time.perf_counter()
        self.lock = threading.Lock()

        # Shared jitter stats (accessed outside main lock via atomic-like updates)
        self.os_jitter = 0.0
        self.samples_collected = 0
        self._stats_lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.perf_counter()

            # --- THE AWARENESS FIX ---
            # If 'now' is much later than our scheduled 'last_refill',
            # it means the CPU task took longer than the rate limit allowed.
            # We reset last_refill to 'now' so we don't carry 'debt' forward.
            if now > self.last_refill + (self.window * 2):
                # (Using 2x window as a buffer, adjust as needed)
                self.tokens = self.capacity
                self.last_refill = now

            # Refill tokens for any small gaps
            if now > self.last_refill:
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + (elapsed * self.rate))
                self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return

                # Reserve next slot
            wait_interval = 1.0 / self.rate
            target_time = self.last_refill + wait_interval
            self.last_refill = target_time

        self._high_precision_sleep(target_time)

    def _high_precision_sleep(self, target):
        now = time.perf_counter()
        sleep_needed = target - now
        if sleep_needed <= 0:
            return

        # Use a safety margin for time.sleep
        with self._stats_lock:
            local_jitter = self.os_jitter
            samples = self.samples_collected

        if samples < 3:
            safety_margin = sleep_needed * 0.6
        else:
            safety_margin = max(local_jitter, sleep_needed * 0.1)

        coarse = sleep_needed - safety_margin

        if coarse > 0:
            t_before = time.perf_counter()
            time.sleep(coarse)
            actual_sleep = time.perf_counter() - t_before

            # Update jitter EMA
            measured_jitter = max(0, actual_sleep - coarse)
            with self._stats_lock:
                self.samples_collected += 1
                alpha = 1.0 / min(20, self.samples_collected)
                self.os_jitter = (self.os_jitter * (1 - alpha)) + (measured_jitter * alpha)

        # Busy-wait until target
        while time.perf_counter() < target:
            pass

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper

class CallLimiterV3:
    """
    Production-ready rate limiter.

    Modes:
    - Burst mode (allow_burst=True):
        Token bucket. Allows bursts up to `calls`.

    - Drip mode (allow_burst=False):
        Strict evenly-spaced calls.

    Features:
    - Thread-safe
    - Adaptive jitter compensation
    - No long busy-wait loops
    """

    def __init__(
            self,
            calls: int,
            period: float = 1.0,
            allow_burst: bool = False,
    ):
        if calls <= 0:
            raise ValueError("calls must be > 0")

        if period <= 0:
            raise ValueError("period must be > 0")

        self.allow_burst = allow_burst

        self.rate = calls / period
        self.period_per_call = period / calls

        self.lock = threading.Lock()

        if allow_burst:
            self.capacity = float(calls)
            self.tokens = float(calls)
            self.last_refill = time.perf_counter()

        else:
            self.next_allowed_time = time.perf_counter()

        self.os_jitter = 0.0
        self.samples_collected = 0
        self.max_samples = 50

    def _learn_jitter(self, requested_sleep: float, actual_sleep: float):
        """
        Learn scheduler oversleep amount using EMA.
        """
        measured_jitter = max(0.0, actual_sleep - requested_sleep)

        with self.lock:
            self.samples_collected += 1

            alpha = 1.0 / min(
                self.samples_collected,
                self.max_samples,
            )

            self.os_jitter = (
                    self.os_jitter * (1.0 - alpha)
                    + measured_jitter * alpha
            )

            # Prevent runaway compensation
            self.os_jitter = min(self.os_jitter, 0.2)

    def _sleep_precise(self, duration: float):
        """
        Sleep with adaptive compensation.

        Avoids long CPU spins while still providing
        relatively accurate wake-up timing.
        """
        if duration <= 0:
            return

        target = time.perf_counter() + duration

        with self.lock:
            local_jitter = self.os_jitter
            local_samples = self.samples_collected

        # Conservative early-learning phase
        if local_samples < 3:
            safety_margin = duration * 0.5
        else:
            safety_margin = max(local_jitter, duration * 0.05)

        coarse_sleep = duration - safety_margin

        if coarse_sleep > 0:
            before = time.perf_counter()

            time.sleep(coarse_sleep)

            actual = time.perf_counter() - before

            self._learn_jitter(coarse_sleep, actual)

        while True:
            remaining = target - time.perf_counter()

            if remaining <= 0:
                return

            # Larger remainder
            if remaining > 0.002:
                time.sleep(0.001)

            # Medium remainder
            elif remaining > 0.0005:
                time.sleep(0.0002)

            # Tiny remainder
            elif remaining > 0.00005:
                time.sleep(0.00001)

            # Final ultra-short spin
            else:
                while time.perf_counter() < target:
                    pass
                return

    def wait(self):
        """
        Block until a call is permitted.
        """
        if self.allow_burst:
            while True:
                with self.lock:
                    now = time.perf_counter()
                    # Correct refill accounting
                    elapsed = now - self.last_refill
                    if elapsed > 0:
                        self.tokens = min(
                            self.capacity,
                            self.tokens + elapsed * self.rate,
                        )

                        # IMPORTANT:
                        # advance refill timestamp immediately
                        self.last_refill = now

                    if self.tokens >= 1.0:
                        self.tokens -= 1.0
                        return

                    wait_time = (1.0 - self.tokens) / self.rate

                self._sleep_precise(wait_time)
        else:
            with self.lock:
                now = time.perf_counter()
                if now > self.next_allowed_time:
                    self.next_allowed_time = now
                allowed_time = self.next_allowed_time
                self.next_allowed_time += self.period_per_call
            wait_time = allowed_time - time.perf_counter()

            if wait_time > 0:
                self._sleep_precise(wait_time)

    def __call__(self, func: Callable) -> Callable:

        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper

class CallLimiterV4:
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

    # ------------------------------------------------------------------
    # JITTER LEARNING
    # ------------------------------------------------------------------

    def _learn_jitter(self, requested_sleep: float, actual_sleep: float):
        """
        Learn average OS sleep overshoot using EMA.
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

    # ------------------------------------------------------------------
    # PRECISE SLEEP
    # ------------------------------------------------------------------

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

        # --------------------------------------------------------------
        # 1. COARSE SLEEP
        # --------------------------------------------------------------
        if coarse_sleep > 0:
            before = time.perf_counter()

            time.sleep(coarse_sleep)

            actual = time.perf_counter() - before

            self._learn_jitter(coarse_sleep, actual)

        # --------------------------------------------------------------
        # 2. FINE SLEEP STAGES
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 3. FINAL MICRO-SPIN
        # --------------------------------------------------------------
        while time.perf_counter() < target:
            pass

    # ------------------------------------------------------------------
    # WAIT
    # ------------------------------------------------------------------

    def wait(self):
        """
        Block until a call is allowed.
        """

        # ==============================================================
        # FIXED WINDOW BURST MODE
        # ==============================================================
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

        # ==============================================================
        # DRIP MODE
        # ==============================================================
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

    # ------------------------------------------------------------------
    # DECORATOR SUPPORT
    # ------------------------------------------------------------------

    def __call__(self, func: Callable) -> Callable:

        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper
