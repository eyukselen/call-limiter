import time
from datetime import datetime
import concurrent.futures
import threading
import os
import sys

# to import as if it is a package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from call_limiter import CallLimiter, CallRetry, ResilientLimiter


# region base run
def base_run():
    def base_func(x):
        print(f"[base_run] called at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} with {x}")

    def pipeline(func):
        start = time.perf_counter()
        repeat = 10
        for x in range(repeat):
            func(x)
        end = time.perf_counter()
        duration = end - start
        print(f"[{func.__name__}] repeated:", repeat, "times in:", f"{duration:.6f}", "seconds")

    print("---start: manual usage---")
    pipeline(base_func)
    print("---end: manual usage---")

# uncomment to run
# base_run()

# endregion


# region call limiter
def simple_limiter():
    def base_func(x):
        print(f"[simple_limiter] called at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} with {x}")

    def pipeline(func):
        start = time.perf_counter()
        repeat = 10
        for x in range(repeat):
            func(x)
        end = time.perf_counter()
        duration = end - start
        print(f"[{func.__name__}] repeated:", repeat, "times in:", f"{duration:.6f}", "seconds")

    print("---start: limiter usage---")
    limiter = CallLimiter(calls=5, period=2, allow_burst=False)
    throttled_func = limiter(base_func)
    start_time = time.perf_counter()
    pipeline(throttled_func)
    end_time = time.perf_counter()
    print(f"limiter total time: {end_time-start_time}")
    print("---end: limiter usage---")

# uncomment to run
# simple_limiter()

# endregion

# region retry
class MockService:
    def __init__(self, fail_first=3):
        self.attempt = 0
        self.fail_first = fail_first
    def request(self, x):
        self.attempt += 1
        if self.attempt < self.fail_first:
            print(f"[Mock Service] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} request with: {x} rejected")
            raise KeyError(f"Failed for request with: {x}")
        else:
            print(f"[Mock Service] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')} request with: {x}")

mock_service = MockService()

retry_manager = CallRetry(retry_count=5, retry_interval=1.0)
resilient_func = retry_manager(mock_service.request)

for x in range(5):
    resilient_func(x)


# endregion

exit()

# region resilientthrottler



class MockDB:
    """a mock service to test throttling and retry for calling too fast"""
    def __init__(self, wcu=5):
        self.wcu = wcu
        self.tokens = float(wcu)
        self.last_check = time.perf_counter()
        # New Counters - to be removed later
        self.success_count = 0
        self.reject_count = 0
        self.lock = threading.Lock()
        # New Counters - to be removed later

    def put_item(self, item_id):
        # New Counters - to be removed later - for thread safety
        with self.lock:  # Ensure thread-safety for token math and counters
        # New Counters - to be removed later - for thread safety
            now = time.perf_counter()
            # Refill tokens based on time passed since the last hit
            self.tokens = min(self.wcu, self.tokens + ((now - self.last_check) * self.wcu))
            self.last_check = now

            if self.tokens >= 1:
                self.tokens -= 1
                self.success_count += 1
                # print(f"[MockDB] {datetime.now()} put item success for item: {item_id}")
                return {"status": 200, "item": item_id, "message": "item stored"}

            # The database is safe, but it's rejecting the client
            # print(f"[MockDB] {datetime.now()} put item reject for item: {item_id}")
            self.reject_count += 1
            return {"status": 429, "item": item_id, "error": "ThrottlingException"}

# let's create a dummy service that throttles us 5 request per second

# region base run without throttler
mock_db = MockDB(wcu=5)

def pipeline():
    for x in range(10):
        response = mock_db.put_item(x)
        # print(response)


# uncomment below to run
# print("---start: without throttler---")
# pipeline()
# print("---end: without throttler---")

# endregion


# region throttler with retry

db_guard = ResilientThrottler(calls=10, period=1.0, allow_burst=False, retry_condition=lambda res: res.get("status") == 429)
mock_db2 = MockDB(wcu=5)
safe_put = db_guard(mock_db2.put_item)

def pipeline():
    for i in range(50):
        # You pass parameters EXACTLY like the original function!
        response = safe_put(i)
        #print(f"Item {i}: {response}")

# uncomment to run
print("---with throttler and retry---")
start_time = time.perf_counter()
pipeline()
end_time = time.perf_counter()
print("total_time:", end_time - start_time)
print(f"success: {mock_db2.success_count} | reject: {mock_db2.reject_count}")
print("---end: with throttler and retry---")

# endregion

# region multi threading - shared throttler with retry

db_guard2 = ResilientThrottler(calls=10, period=1.0, allow_burst=False, retry_condition=lambda res: res.get("status") == 429)
mock_db3 = MockDB(wcu=5)
safe_put2 = db_guard(mock_db3.put_item)

# uncomment to run
print("---start: multi threading - shared throttler with retry---")
start_time = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    # 10 threads competing for the SAME tokens
    executor.map(safe_put2, range(50))
end_time = time.perf_counter()
print("total_time:", end_time - start_time)
print(f"success: {mock_db3.success_count} | reject: {mock_db3.reject_count}")
print("---end: multi threading - shared throttler with retry---")

# endregion

# region multi threading - private throttler with retry - each thread has its own

def independent_worker(item_id):
    # Each time this is called, a BRAND NEW throttler is born
    # It starts with a FRESH "Full Tank" of 5.0 tokens (from MockDB's perspective)
    local_guard = ResilientThrottler(calls=10, period=1.0, allow_burst=False,
                                     retry_condition=lambda res: res.get("status") == 429)

    # Wrap the shared mock_db4 call locally
    local_safe_put = local_guard(mock_db4.put_item)
    return local_safe_put(item_id)

mock_db4 = MockDB(wcu=5)

# uncomment to run
print("---start: multi threading - private throttler with retry---")
start_time = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    # Now, each of the 5 workers manages its own speed
    executor.map(independent_worker, range(50))
end_time = time.perf_counter()
print("total_time:", end_time - start_time)
print(f"success: {mock_db4.success_count} | reject: {mock_db4.reject_count}")
print("---end: multi threading - private throttler with retry---")
# endregion

exit()

print("---start: rate limit---")

@RateLimitRetry(calls=5, period=2)
def base_func_decoratored(x):
    print("called with:", x)

start = time.perf_counter()
repeat = 10
for x in range(repeat):
    base_func_decoratored(x)
end = time.perf_counter()
duration = end - start
print("repeated:", repeat, "times in:", f"{duration:.6f}", "seconds")

@RateLimitRetry(calls=5, period=2)
def base_func_decoratored2(x):
    print("called with:", x)

pipeline(base_func_decoratored2)

print("---end: rate limit---")


# TODO: how this should be used: may be decorator is not the best way
limiter = RateLimitRetry(calls=5, period=2)

def my_function(x):
    print(f"Working on {x}")

# Use Case A: Fast/Internal (No limit)
for i in range(10):
    my_function(i)

# Use Case B: Talking to a strict API (Limited)
for i in range(10):
    with limiter:
        my_function(i)
# TODO: or ...
# The original remains "free"
def download(url): ...

# Create a restricted version for a specific task
download_throttled = limiter(download)

# Use the throttled one for the public API
download_throttled("https://api.com")

# TODO: or...
limiter = RateLimitRetry(5, 2)

def loop():
    limiter._wait_if_needed() # Manual gate
    raw_function()