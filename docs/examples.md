# Examples

## CallLimiter

### Burst Mode (5 calls per 2 seconds)

All 5 calls fire instantly, then the limiter waits for the next period:

```python
from call_limiter import CallLimiter

limiter = CallLimiter(calls=5, period=2, allow_burst=True)
throttled_func = limiter(my_function)

for i in range(10):
    throttled_func(i)
```

### Drip Mode (5 calls per 2 seconds, evenly spaced)

Calls are spaced every 0.4 seconds (2s / 5 calls):

```python
from call_limiter import CallLimiter

limiter = CallLimiter(calls=5, period=2, allow_burst=False)
throttled_func = limiter(my_function)

for i in range(10):
    throttled_func(i)
```

---

## CallRetry

### Retry with Logging and Fallback

Retries up to 5 times on `ValueError`, logs each retry, and falls back if all attempts fail:

```python
from call_limiter import CallRetry

def retry_logger(exception, attempt_number):
    print(f"Retry #{attempt_number}: {exception}")

def fail_handler(exception):
    print(f"All retries exhausted: {exception}")
    return "fallback_value"

retry = CallRetry(
    retry_count=5,
    retry_interval=0.5,
    retry_exceptions=(ValueError,),
    on_retry=retry_logger,
    fallback=fail_handler
)
resilient_func = retry(my_function)
result = resilient_func()
```

### Retry without Fallback

If no fallback is provided, the last exception is raised after all retries are exhausted:

```python
from call_limiter import CallRetry

retry = CallRetry(
    retry_count=3,
    retry_interval=1.0,
    retry_exceptions=(ValueError,)
)
resilient_func = retry(my_function)
```

---

## ResilientLimiter

### Rate-Limited Retries with Burst

Each retry respects the rate limiter's pace:

```python
from call_limiter import ResilientLimiter

def retry_handler(exception, attempt_number):
    print(f"Retry #{attempt_number}: {exception}")

def fallback_handler(exception):
    print(f"All retries exhausted: {exception}")
    return "fallback_value"

limiter = ResilientLimiter(
    calls=5,
    period=1,
    allow_burst=True,
    retry_count=3,
    on_retry=retry_handler,
    fallback=fallback_handler
)

@limiter
def my_function(x):
    pass

for x in range(5):
    result = my_function(x)
```

### Rate-Limited Retries with Drip

Same as above but calls are evenly spaced, including retries:

```python
from call_limiter import ResilientLimiter

limiter = ResilientLimiter(
    calls=5,
    period=1,
    allow_burst=False,
    retry_count=2,
    on_retry=retry_handler,
    fallback=fallback_handler
)

@limiter
def my_function(x):
    pass
```
