import time
from datetime import datetime
import concurrent.futures
import threading
import os
import sys

# to import as if it is a package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from call_limiter import CallLimiter, CallRetry, ResilientLimiter


# region call limiter
def call_limiter_example(calls=5, period=2,burst=True, total_calls=10):

    # base function to rate limit
    def base_func(x):
        print(f"    [CallLimiter] called at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} with call: {x} of {total_calls}")

    # pipeline to call base_func repeatedly
    def pipeline(func):
        start = time.perf_counter()
        for x in range(1, total_calls + 1):
            func(x)
        end = time.perf_counter()
        duration = end - start
        print(f"    [{func.__name__}] called:", total_calls, "times in:", f"{duration:.6f}", "seconds")

    print(f"---start: CallLimiter running for: {calls} calls per {period} seconds with burst={burst} for a total of {total_calls} calls ---")

    # usage: example
    limiter = CallLimiter(calls=calls, period=period, allow_burst=burst)
    throttled_func = limiter(base_func)
    pipeline(throttled_func)
    # usage: example

    print("---end: CallLimiter---\n")

# uncomment to run
# call_limiter_example(calls=5, period=2,burst=True, total_calls=10)
# call_limiter_example(calls=5, period=2,burst=False, total_calls=10)

# endregion


# region retry
def call_retry_example(retry_count=3, retry_interval=0.5, fail_first=3):

    # a flaky function that fails the first N attempts then succeeds
    attempt = {"count": 0}

    def flaky_function():
        attempt["count"] += 1
        if attempt["count"] <= fail_first:
            print(f"    [CallRetry] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} attempt {attempt['count']} - FAILED")
            raise ValueError(f"Simulated failure on attempt {attempt['count']}")
        print(f"    [CallRetry] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} attempt {attempt['count']} - SUCCESS")
        return "result"

    # logger to log retry attempts
    def retry_logger(exception, attempt_number):
        print(f"    [on_retry] retry #{attempt_number}: {exception}")

    # fail handler to handle final action if still failed after all attempts
    def fail_handler(exception):
        print(f"    [fallback] all retries exhausted: {exception}")
        return "fallback_value"

    print(f"---start: CallRetry with retry_count={retry_count}, retry_interval={retry_interval}s, fail_first={fail_first} ---")

    # usage: example
    retry = CallRetry(
        retry_count=retry_count,
        retry_interval=retry_interval,
        retry_exceptions=(ValueError,),
        on_retry=retry_logger,
        fallback=fail_handler
    )
    resilient_func = retry(flaky_function)
    # usage: example

    start = time.perf_counter()
    result = resilient_func()
    duration = time.perf_counter() - start
    print(f"    Result: {result} in {duration:.6f} seconds")

    print("---end: CallRetry---\n")

# uncomment to run
# call_retry_example(retry_count=5, retry_interval=0.5, fail_first=3)   # succeeds after 3 failures
# call_retry_example(retry_count=2, retry_interval=0.5, fail_first=10)  # exhausts retries, hits fallback

# endregion


# region resilient limiter
def resilient_limiter_example(calls=5, period=1, burst=True, retry_count=3, fail_first=2, total_calls=5):

    # a flaky function that fails the first N attempts then succeeds
    attempt = {"count": 0}

    def flaky_function(x):
        attempt["count"] += 1
        if attempt["count"] <= fail_first:
            print(f"    [ResilientLimiter] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} call {x} attempt {attempt['count']} - FAILED")
            raise ValueError(f"Simulated failure on attempt {attempt['count']}")
        print(f"    [ResilientLimiter] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} call {x} attempt {attempt['count']} - SUCCESS")
        return f"result_{x}"

    def retry_handler(exception, attempt_number):
        print(f"    [on_retry] retry #{attempt_number}: {exception}")

    def fallback_handler(exception):
        print(f"    [fallback] all retries exhausted: {exception}")
        return "fallback_value"

    print(f"---start: ResilientLimiter with calls={calls}/{period}s burst={burst}, retry_count={retry_count}, fail_first={fail_first} ---")

    # usage: example
    limiter = ResilientLimiter(
        calls=calls,
        period=period,
        allow_burst=burst,
        retry_count=retry_count,
        on_retry=retry_handler,
        fallback=fallback_handler
    )
    throttled_func = limiter(flaky_function)
    # usage: example

    start = time.perf_counter()
    for x in range(1, total_calls + 1):
        attempt["count"] = 0  # reset per call
        result = throttled_func(x)
        print(f"    Result for call {x}: {result}")
    duration = time.perf_counter() - start
    print(f"    Total: {total_calls} calls in {duration:.6f} seconds")

    print("---end: ResilientLimiter---\n")

# uncomment to run
resilient_limiter_example(calls=5, period=1, burst=True, retry_count=3, fail_first=2, total_calls=5)
resilient_limiter_example(calls=5, period=1, burst=False, retry_count=2, fail_first=10, total_calls=3)

# endregion
