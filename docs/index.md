# call-limiter 🚀

Thread-safe Python decorators for synchronized rate limiting and retry logic.

## Core Components

* **CallLimiter**: A high-precision throttler that paces function calls to stay within specific rate limits.
* **CallRetry**: A resilience decorator that re-runs failed functions with a configurable delay and exception handling.
* **ResilientLimiter**: A hybrid solution that combines pacing with coordinated recovery, ensuring retries never exceed your defined rate limit across threads.

## Installation

```
pip install call-limiter
```

## Key Features

* **Low-Jitter Timing**: Uses `time.perf_counter()` and resolution-aware sleeping to prevent the "creeping delays" common in standard rate limiters.
* **Zero-Hardcode Logic**: Accounts for OS jitter to ensure `time.sleep` remains accurate even under system load.
* **Thread-Safe**: Designed for multithreaded environments where multiple workers hit the same limited resource.
* **Thread-Synchronized State**: Shared locks ensure that multiple threads hitting the same limiter behave as a single unit.
* **Synchronized Pacing**: In hybrid mode, retries are queued through the global limiter, preventing a "thundering herd" and ensuring you never exceed your quota during recovery.
