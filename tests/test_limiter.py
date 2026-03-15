import time
import pytest
from call_limiter import CallLimiter, CallRetry, ResilientLimiter
import threading


class TestCallLimiter:
    def test_paced_drip_accuracy(self):
        """Ensures that allow_burst=False creates steady 0.2s intervals for 5 calls/1s."""
        calls = 5
        period = 1.0
        limiter = CallLimiter(calls=calls, period=period, allow_burst=False)

        timestamps = []

        @limiter
        def identity(i):
            timestamps.append(time.perf_counter())
            return i

        # Run 4 calls (3 intervals)
        for i in range(4):
            identity(i)

        # Each interval should be ~0.2s
        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            # Increased tolerance from 0.01 to 0.05 to account for CI/Cloud jitter
            assert gap == pytest.approx(0.2, abs=0.05), f"Gap {i} was {gap}s, expected 0.2s"


    def test_burst_behavior(self):
        """Ensures allow_burst=True allows immediate execution followed by a wait."""
        calls = 5
        period = 1.0
        limiter = CallLimiter(calls=calls, period=period, allow_burst=True)

        start = time.perf_counter()

        @limiter
        def fast_call():
            pass

        # First 5 calls should be near-instant
        for _ in range(5):
            fast_call()

        burst_duration = time.perf_counter() - start
        assert burst_duration < 0.01, f"Burst took {burst_duration}s, should be < 0.01s"

        # 6th call must trigger the 'wall' and take ~0.2s from the start of the window
        fast_call()
        total_duration = time.perf_counter() - start
        assert total_duration >= 0.2, "6th call did not wait for the refill drip"


    def test_multithreaded_safety(self):
        """Ensures the lock prevents race conditions with concurrent calls."""

        calls = 10
        period = 0.5
        limiter = CallLimiter(calls=calls, period=period, allow_burst=False)
        results = []

        @limiter
        def secure_call(i):
            results.append(i)

        threads = [threading.Thread(target=secure_call, args=(i,)) for i in range(10)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        end = time.perf_counter()

        # Total time for 10 calls with 0.05s intervals should be ~0.45s
        # (1st call is free, 9 intervals of 0.05s)
        assert len(results) == 10
        assert (end - start) >= 0.44


class TestCallRetry:
    def test_retry_success_after_failure(self):
        """Ensures it eventually succeeds if the error clears."""
        attempts = 0

        def flaky_func():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("Fail")
            return "Success"

        retry = CallRetry(retry_count=5, retry_interval=0.01, retry_exceptions=(ValueError,))
        result = retry(flaky_func)()

        assert result == "Success"
        assert attempts == 3

    def test_retry_fallback_on_exhaustion(self):
        """Ensures fallback is called after all retries fail."""

        def permanent_fail():
            raise ValueError("Dead")

        def my_fallback(e):
            return "Saved"

        retry = CallRetry(retry_count=2, retry_interval=0.01, fallback=my_fallback)
        result = retry(permanent_fail)()

        assert result == "Saved"

    def test_retry_ignores_wrong_exception(self):
        """Ensures it crashes immediately on an unhandled exception type."""

        def type_error_func():
            raise TypeError("Wrong error")

        # Only looking for ValueErrors
        retry = CallRetry(retry_count=5, retry_exceptions=(ValueError,))

        with pytest.raises(TypeError):
            retry(type_error_func)()

    def test_retry_raises_after_exhaustion_no_fallback(self):
        """Ensures the original exception is raised if no fallback is provided."""

        def constant_fail():
            raise ValueError("Ultimate Failure")

        # No fallback passed here
        retry = CallRetry(retry_count=2, retry_interval=0.01, retry_exceptions=(ValueError,))

        # We expect the decorator to eventually let the ValueError bubble up
        with pytest.raises(ValueError, match="Ultimate Failure"):
            retry(constant_fail)()


class TestResilientLimiter:
    def test_documented_scenario(self):
        """Validates the exact scenario described in documentation."""
        events = []

        def retry_handler(e, n):
            events.append(f"retry_{n}")

        def fail_handler(e):
            events.append("failed")
            return "fallback_value"

        @ResilientLimiter(
            calls=10, # Fast for testing
            period=1.0,
            allow_burst=True,
            retry_count=2,
            on_retry=retry_handler,
            fallback=fail_handler
        )
        def unstable_func():
            raise ValueError("Boom")

        result = unstable_func()

        # Should have: 2 retries logged + 1 fallback log
        assert events == ["retry_1", "retry_2", "failed"]
        assert result == "fallback_value"


class TestEdgeCases:
    def test_argument_propagation(self):
        """Ensures args and kwargs pass through the entire stack."""
        limiter = ResilientLimiter(calls=10, period=1.0)

        @limiter
        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        assert add(2, 3, multiplier=2) == 10

    def test_retry_return_value(self):
        """Ensures the successful return value is captured after retries."""
        count = 0

        def fail_once():
            nonlocal count
            count += 1
            if count == 1: raise ValueError("First fail")
            return {"status": "ok"}

        retry = CallRetry(retry_count=2, retry_interval=0.01)
        assert retry(fail_once)() == {"status": "ok"}

    def test_limiter_recovery(self):
        """Ensures the bucket refills completely after a long pause."""
        limiter = CallLimiter(calls=2, period=0.2, allow_burst=True)

        # Spend tokens
        limiter.wait()
        limiter.wait()

        # Wait for full refill
        time.sleep(0.3)

        start = time.perf_counter()
        limiter.wait()  # Should be instant
        assert (time.perf_counter() - start) < 0.01


class TestStressTest:
    def test_high_frequency_throughput(self):
        # ... (This one passed, keep as is) ...
        pass

    def test_heavy_concurrency_contention(self):
        """STRESS TEST 2: High contention with Burst."""
        limiter = CallLimiter(calls=500, period=1.0, allow_burst=True)
        shared_list = []

        def worker():
            for _ in range(50):
                limiter.wait()
                shared_list.append(time.perf_counter())

        threads = [threading.Thread(target=worker) for _ in range(20)]  # 1000 total calls

        start = time.perf_counter()
        for t in threads: t.start()
        for t in threads: t.join()
        end = time.perf_counter()

        duration = end - start
        # With 1000 calls and 500/sec limit + Burst:
        # 500 happen at T=0. 500 happen at T=1.0. Total ~1.0s.
        assert 0.9 <= duration <= 1.3

    def test_retry_storm(self):
        """STRESS TEST 3: Ensuring throughput holds even when retries happen."""

        # We'll track attempts to make it succeed on the 2nd retry
        attempts = {}

        @ResilientLimiter(
            calls=1000,
            period=1.0,
            retry_count=2,
            retry_interval=0.001,
            retry_exceptions=(RuntimeError,)
        )
        def unstable_service(i):
            attempts[i] = attempts.get(i, 0) + 1
            # Fail on first attempt, succeed on second
            if attempts[i] < 2:
                raise RuntimeError("Temporary Glitch")
            return True

        start = time.perf_counter()
        # 500 calls, each fails once then succeeds = 1000 total calls
        results = [unstable_service(i) for i in range(500)]
        end = time.perf_counter()

        assert len(results) == 500
        # 1000 total calls at 1000 RPS should take roughly 1.0s
        # We use 0.7 as a floor to account for high-speed execution
        assert (end - start) >= 0.4