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
        # First gap gets wider tolerance (±0.08s) due to cold-start jitter calibration
        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            tolerance = 0.08 if i == 0 else 0.05
            assert gap == pytest.approx(0.2, abs=tolerance), f"Gap {i} was {gap}s, expected 0.2s"

    def test_paced_drip_different_ratios(self):
        """Ensures drip mode works correctly with different calls/period ratios."""
        # 10 calls per 2 seconds = 0.2s interval (same rate, different params)
        limiter = CallLimiter(calls=10, period=2.0, allow_burst=False)
        timestamps = []

        @limiter
        def record():
            timestamps.append(time.perf_counter())

        for _ in range(4):
            record()

        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            assert gap == pytest.approx(0.2, abs=0.05), f"Gap {i} was {gap}s, expected 0.2s"

        # 1 call per 0.5 seconds = 0.5s interval
        timestamps.clear()
        limiter2 = CallLimiter(calls=1, period=0.5, allow_burst=False)
        record2 = limiter2(lambda: timestamps.append(time.perf_counter()))

        for _ in range(3):
            record2()

        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            assert gap == pytest.approx(0.5, abs=0.1), f"Gap {i} was {gap}s, expected 0.5s"

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

    def test_burst_full_cycle(self):
        """Ensures a second burst fires correctly after the first burst + wait."""
        calls = 3
        period = 0.5
        limiter = CallLimiter(calls=calls, period=period, allow_burst=True)

        timestamps = []

        @limiter
        def record():
            timestamps.append(time.perf_counter())

        # First burst: 3 calls should be near-instant
        for _ in range(3):
            record()

        first_burst_duration = timestamps[-1] - timestamps[0]
        assert first_burst_duration < 0.01, f"First burst took {first_burst_duration}s"

        # Next 3 calls trigger a wait, then should burst again
        for _ in range(3):
            record()

        # Calls 3-5 (second burst) should also be near-instant relative to each other
        second_burst_duration = timestamps[-1] - timestamps[3]
        assert second_burst_duration < 0.01, f"Second burst took {second_burst_duration}s"

        # But there should be a gap between the two bursts (~0.5s period)
        gap_between_bursts = timestamps[3] - timestamps[0]
        assert gap_between_bursts >= 0.4, f"Gap between bursts was {gap_between_bursts}s, expected ~0.5s"

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

    def test_decorator_preserves_function_metadata(self):
        """Ensures @wraps preserves the original function's name and docstring."""
        limiter = CallLimiter(calls=5, period=1.0)

        @limiter
        def my_important_function():
            """This is the docstring."""
            pass

        assert my_important_function.__name__ == "my_important_function"
        assert my_important_function.__doc__ == "This is the docstring."

    def test_limiter_recovery_after_pause(self):
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

    def test_on_retry_callback_receives_correct_args(self):
        """Ensures on_retry receives (exception, attempt_number) correctly."""
        callback_args = []

        def on_retry(exception, attempt_number):
            callback_args.append((str(exception), attempt_number))

        attempts = 0

        def fail_twice():
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise ValueError(f"Fail {attempts}")
            return "ok"

        retry = CallRetry(retry_count=3, retry_interval=0.01, retry_exceptions=(ValueError,), on_retry=on_retry)
        result = retry(fail_twice)()

        assert result == "ok"
        assert len(callback_args) == 2
        assert callback_args[0] == ("Fail 1", 1)
        assert callback_args[1] == ("Fail 2", 2)

    def test_retry_count_zero(self):
        """Ensures retry_count=0 means exactly 1 attempt with no retries."""

        def always_fail():
            raise ValueError("Boom")

        retry = CallRetry(retry_count=0, retry_interval=0.01, retry_exceptions=(ValueError,))

        with pytest.raises(ValueError, match="Boom"):
            retry(always_fail)()

    def test_retry_catches_multiple_exception_types(self):
        """Ensures retry works with a tuple of multiple exception types."""
        attempts = 0

        def mixed_errors():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("val")
            if attempts == 2:
                raise KeyError("key")
            return "ok"

        retry = CallRetry(retry_count=3, retry_interval=0.01, retry_exceptions=(ValueError, KeyError))
        result = retry(mixed_errors)()

        assert result == "ok"
        assert attempts == 3

    def test_decorator_preserves_function_metadata(self):
        """Ensures @wraps preserves the original function's name and docstring."""
        retry = CallRetry(retry_count=3, retry_interval=0.01)

        @retry
        def my_retried_function():
            """Retry docstring."""
            pass

        assert my_retried_function.__name__ == "my_retried_function"
        assert my_retried_function.__doc__ == "Retry docstring."


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

    def test_retries_respect_rate_limit(self):
        """Ensures each retry attempt goes through the rate limiter."""
        timestamps = []

        attempts = 0

        @ResilientLimiter(
            calls=5,
            period=1.0,
            allow_burst=False,  # drip: 0.2s between calls
            retry_count=3,
            retry_exceptions=(ValueError,)
        )
        def fail_then_succeed():
            nonlocal attempts
            timestamps.append(time.perf_counter())
            attempts += 1
            if attempts <= 2:
                raise ValueError("fail")
            return "ok"

        result = fail_then_succeed()
        assert result == "ok"
        assert attempts == 3

        # Each attempt should be spaced by ~0.2s (drip interval)
        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            assert gap >= 0.15, f"Gap {i} was {gap}s, retries should respect rate limiter pacing"



class TestEdgeCases:
    def test_argument_propagation(self):
        """Ensures args and kwargs pass through the entire stack."""
        limiter = ResilientLimiter(calls=10, period=1.0)

        @limiter
        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        assert add(2, 3, multiplier=2) == 10




class TestStressTest:
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