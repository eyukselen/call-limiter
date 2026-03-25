# Getting Started

## Installation

```
pip install call-limiter
```

## Quick Start

### Rate Limiting with Burst

Fire all 5 calls instantly, then wait for the next period:

```python
from call_limiter import CallLimiter

limiter = CallLimiter(calls=5, period=1, allow_burst=True)
throttled_func = limiter(my_function)
```

### Rate Limiting with Drip (Evenly Spaced)

Spread calls evenly — one call every 0.2 seconds:

```python
from call_limiter import CallLimiter

limiter = CallLimiter(calls=5, period=1, allow_burst=False)
throttled_func = limiter(my_function)
```

### Retry on Failure

Retry up to 5 times with 1-second delay, log each retry, and use a fallback if all retries fail:

```python
from call_limiter import CallRetry

retry = CallRetry(
    retry_count=5,
    retry_interval=1.0,
    retry_exceptions=(ValueError,),
    on_retry=retry_logger,
    fallback=fail_handler
)
resilient_func = retry(my_function)
```

### Rate Limiting + Retry Combined

Rate limit your calls and automatically retry failures — each retry respects the rate limit:

```python
from call_limiter import ResilientLimiter

limiter = ResilientLimiter(
    calls=5,
    period=1.0,
    allow_burst=True,
    retry_count=3,
    on_retry=retry_handler,
    fallback=fail_handler
)

@limiter
def my_function():
    pass
```
