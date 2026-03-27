# 🚀 v1.0.0 — First Stable Release

Thread-safe rate limiting and retry logic for Python — zero dependencies, high-precision timing, production-ready.

## Core Components

- **`CallLimiter`** — High-precision, thread-safe rate limiter with burst and drip (evenly-spaced) modes using a token bucket algorithm
- **`CallRetry`** — Thread-safe, configurable retry decorator with logging callbacks and fallback support
- **`ResilientLimiter`** — Thread-safe combined rate limiting + retry where every attempt (including retries) respects the rate limit

## Highlights

- ⏱️ **Adaptive Jitter Compensation** — Hybrid `time.sleep()` + busy-wait with learned OS jitter for sub-millisecond precision across all platforms
- 🔒 **Thread-Safe** — All three classes are safe for concurrent use across multiple threads
- 🐍 **Python 3.8–3.14** — Tested on Ubuntu, macOS, and Windows via GitHub Actions CI
- 📦 **Zero Dependencies** — Pure Python, nothing extra to install
- ✅ **100% Test Coverage** — Unit tests, edge cases, multithreaded safety, and stress tests

## Quick Start

```python
from call_limiter import CallLimiter

# 5 calls per second, evenly spaced (one every 0.2s)
limiter = CallLimiter(calls=5, period=1.0, allow_burst=False)

@limiter
def call_api():
    pass
```

📖 [Full Documentation](https://call-limiter.readthedocs.io/) · 💻 [Source Code](https://github.com/eyukselen/call-limiter)
