import time
import threading
from functools import wraps


class CallLimiter:
    """CASE 1: The Pacer. Focuses on hardware-calibrated execution speed."""

    def __init__(self, calls: int, period: float = 1.0, allow_burst: bool = False):
        self.rate = calls / period
        self.capacity = float(calls) if allow_burst else 1.0
        self.tokens = self.capacity
        self.last_refill = time.perf_counter()
        self.lock = threading.Lock()

        # Zero-Hardcode: Hardware Calibration
        t0 = time.perf_counter()
        _ = time.perf_counter()
        self.pulse = time.perf_counter() - t0
        self.os_jitter = 0.0

    def wait(self):
        with self.lock:
            now = time.perf_counter()
            self.tokens = min(self.capacity, self.tokens + ((now - self.last_refill) * self.rate))
            self.last_refill = now

            if self.tokens < 1.0:
                target_tokens = self.capacity
                sleep_needed = (target_tokens - self.tokens) / self.rate

                if sleep_needed > self.os_jitter:
                    t_before = time.perf_counter()
                    time.sleep(max(0, sleep_needed - self.os_jitter))
                    actual_sleep = time.perf_counter() - t_before
                    self.os_jitter = max(self.os_jitter, actual_sleep - sleep_needed)

                while ((self.last_refill + sleep_needed) - time.perf_counter()) > self.pulse:
                    pass

                self.tokens = target_tokens
                self.last_refill = time.perf_counter()
            self.tokens -= 1.0

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)

        return wrapper


class CallRetry:
    """CASE 2: The Rescuer. Focuses on resilience and the Master Brake."""

    def __init__(self, retry_count: int = 3, retry_interval: float = 1.0,
                 retry_exceptions: tuple = None, on_retry: callable = None):
        self.retry_count = retry_count
        self.retry_interval = retry_interval
        self.retry_exceptions = retry_exceptions or (Exception,)
        self.on_retry = on_retry
        self.lock = threading.Lock()
        self.is_braking = False

        t0 = time.perf_counter()
        self.pulse = time.perf_counter() - t0

    def _trigger_recovery(self, attempt):
        if attempt >= self.retry_count:
            return False
        with self.lock:
            self.is_braking = True

        time.sleep(max(0, self.retry_interval))

        with self.lock:
            self.is_braking = False
        return True

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                while self.is_braking:
                    time.sleep(self.pulse)
                try:
                    return func(*args, **kwargs)
                except self.retry_exceptions as e:
                    if self.on_retry:
                        self.on_retry(e, attempt + 1)
                    if self._trigger_recovery(attempt):
                        attempt += 1
                        continue
                    raise e

        return wrapper


class ResilientLimiter(CallLimiter):
    """CASE 3: The Hybrid. Pacing + Resilience for production pipelines."""

    def __init__(self, calls, period=1.0, retry_count=3, retry_interval=1.0,
                 retry_exceptions=None, on_retry=None):
        super().__init__(calls, period)
        self.retry_count = retry_count
        self.retry_interval = retry_interval
        self.retry_exceptions = retry_exceptions or (Exception,)
        self.on_retry = on_retry

    def _trigger_recovery(self, attempt):
        if attempt >= self.retry_count:
            return False
        with self.lock:
            self.tokens = 0.0  # Master Brake: Drain the bucket
        time.sleep(max(0, self.retry_interval))
        return True

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                self.wait()
                try:
                    return func(*args, **kwargs)
                except self.retry_exceptions as e:
                    if self.on_retry:
                        self.on_retry(e, attempt + 1)
                    if self._trigger_recovery(attempt):
                        attempt += 1
                        continue
                    raise e

        return wrapper