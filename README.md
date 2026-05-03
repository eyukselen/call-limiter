# call-limiter ⏱️♻️🛡️

[![PyPI - Version](https://img.shields.io/pypi/v/call-limiter?color=blue&cache_bust=1)](https://pypi.org/project/call-limiter/)
[![Documentation](https://readthedocs.org/projects/call-limiter/badge/?version=latest)](https://call-limiter.readthedocs.io/en/latest/?badge=latest)
[![Build Status](https://github.com/eyukselen/call-limiter/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/eyukselen/call-limiter/actions)
[![Python Versions](https://img.shields.io/pypi/pyversions/call-limiter)](https://pypi.org/project/call-limiter/)
[![License](https://img.shields.io/pypi/l/call-limiter?color=orange)](https://opensource.org/licenses/MIT)

A high-precision concurrency control library for distributed systems resilience.

<img src="https://raw.githubusercontent.com/eyukselen/call-limiter/main/docs/assets/call_limiter_thumbnail.png" alt="Call-Limiter Design" width="500">

## ✨ Key Features

* Low-Jitter Timing: Uses time.perf_counter() and resolution-aware sleeping to prevent the "creeping delays" common in standard rate limiters.
* Dynamic Jitter Compensation: Automatically adjusts for OS-level scheduling delays to ensure time.sleep intervals remain precise under heavy system load.
* Thread-Safe: Designed for multithreaded environments where multiple workers hit the same limited resource.
* Thread-Synchronized State: Shared locks ensure that 10 threads hitting the same limiter behave as a single unit.
* Synchronized Pacing: In hybrid mode, retries are queued through the global limiter, preventing a 'thundering herd' and ensuring you never exceed your quota during recovery.

---
## 📦 Core Components

* ⏱️ **CallLimiter**: A high-precision throttler that paces function calls to stay within specific rate limits.


<details>
<summary><b>⏱️ View Throttling Strategy Diagram</b></summary>

```
Burst mode for 5 calls per 10 seconds:  
Time (s)  0              5              10                            20
          |-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----  
Call-1    [████]                        |                             |
Call-2    [█████]                       |                             |
Call-3    [██]                          |                             |
Call-4    [█████]                       |                             |
Call-5    [█]                           |                             |
Call-6                                  |[████]                       |  
Call-7                                  |[█████]                      |       
Call-8                                  |[██]                         |        
Call-9                                  |[█████]                      |     
Call-10                                 |[█]                          |     

Drip mode for 5 calls per 10 seconds:
Time (s)  0              5              10                            20
          |-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
Call-1    [████]                        |                             |
Call-2          [█████]                 |                             |
Call-3                [██]              |                             |
Call-4                      [█████]     |                             |
Call-5                            [█]   |                             |
Call-6                                  |[████]                       | 
Call-7                                  |      [█████]                |
Call-8                                  |            [██]             |
Call-9                                  |                 [█████]     |
Call-10                                 |                       [█]   |
```
</details>



* ♻️ **CallRetry**: A resilience decorator that re-runs failed functions with a configurable delay and exception handling.

<details>
<summary><b>⏱️ View Retry Strategy Diagram</b></summary>

```mermaid
sequenceDiagram
    autonumber
    participant App as "Client Code"
    participant R as "CallRetry Decorator"
    participant API as "Downstream Service"

    App->>R: Invoke Function
    
    loop "Up to max_retry times"
        R->>API: Attempt Execution
        alt "Success"
            API-->>R: Return Data
            R-->>App: Return Result
        else "Error (Retryable)"
            Note over R, API: "Trigger on_retry hook"
            R->>R: "Wait (retry_interval)"
        end
    end

    alt "All Attempts Exhausted"
        R->>R: "Execute fallback_handler"
        R-->>App: "Return Fallback Result"
    else "No Fallback"
        R-->>App: "Raise Final Exception"
    end

``` 

</details>

* 🛡️ **ResilientLimiter**: A hybrid solution that combines pacing with Coordinated Recovery, ensuring retries never exceed your defined rate limit across threads.

<details>
<summary><b>⏱️ View Resilient Strategy Diagram</b></summary>

```mermaid
sequenceDiagram
    autonumber
    participant App as "Client Code"
    participant RL as "ResilientLimiter"
    participant L as "Shared CallLimiter"
    participant API as "Downstream Service"

    App->>RL: Invoke Function
    
    loop "Retry Loop (Max 3)"
        Note over RL, L: Check Rate Limit Contract
        RL->>L: Request Execution Slot
        L->>L: Calculate Window (perf_counter)
        L-->>RL: Slot Granted (after Paced Wait)
        
        RL->>API: Attempt Execution
        
        alt "Success"
            API-->>RL: 200 OK
            RL-->>App: Return Result
        else "Error"
            Note over RL: Trigger on_retry
            RL->>RL: Backoff Delay
        end
    end
    
    alt "Final Failure"
        RL->>RL: Execute Fallback
        RL-->>App: Fallback Result
    end
```

</details>

## 🛠 Installation

```
pip install call-limiter
```

---

## Usage

### Component 1: ⏱️ CallLimiter  

**Scenario:** I want to "rate limit" (throttle) my function so it limits my calls to 5 calls per second. I also want to have an option to select if I want 5 calls to fire instantly or spread across evenly in the 1 second period.

**Usage-1: 5 calls per 1 second with burst (instantly fire all 5 calls)**
*Best for: Maximizing throughput when the target API allows short spikes.*

**My function to throttle:** `my_function`

```python
from call_limiter import CallLimiter

limiter = CallLimiter(calls=5, period=1, allow_burst=True)
throttled_func = limiter(my_function)
```

**Usage-2: 5 calls per 1 second paced (evenly spread calls)**
*Best for: Avoiding "spiky" traffic patterns that trigger anti-bot protections.*

```python

from call_limiter import CallLimiter

# This forces a call exactly every 0.2 seconds (1s / 5 calls)
limiter = CallLimiter(calls=5, period=1, allow_burst=False)
throttled_func = limiter(my_function)
```

---
### Component 2: ♻️ CallRetry

**Scenario:** I want a retry logic to use with my function calls. 
If `my_function` raises ValueError exception, it should retry up to 5 times with 1-second delay between attempts.
I want to log every retry with `retry_logger` function.
if it still fails, it should use `fail_handler` function. (if not provided, raise error)

```python
from call_limiter import CallRetry

# This configuration perfectly mirrors your scenario:
retry = CallRetry(
    retry_count=5,
    retry_interval=1.0,
    retry_exceptions=(ValueError,), # Trigger
    on_retry=retry_logger,           # Observability
    fallback=fail_handler            # Outcome (Plan B)
)

# If fail_handler is a function, this returns its result on ultimate failure.
# If you didn't pass fail_handler, it would raise the ValueError.
resilient_func = retry(my_function)
```

---
### Component 3: 🛡️ ResilientLimiter
**Scenario:** I want a rate limiter that can also handle failed calls. `my_function` should be called  
Flow Logic:
* 5 calls/per second with burst (or drip), 
* max_retry = 3 (if it fails) 
* on_retry=`retry_handler`, notify me by calling optional `retry_handler`, if not provided ignore!
* fallback=`falback_handler` if it still fails notify me, if not provided raise error!
Note: each retry will comply "5 calls/per second with burst (or drip)" tempo to respect rate limiter  
Note: on_retry receives (exception, attempt_number), while fallback is a simple callable.

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
    # This will respect the 5/sec pace, even during retries.
    pass
```

---
## 📋 Links
* [![Docs](https://img.shields.io/badge/Docs-white?logo=readthedocs&logoColor=8CA1AF)](https://call-limiter.readthedocs.io/)
* [![PyPI](https://img.shields.io/badge/PyPI-white?logo=pypi&logoColor=3775A9)](https://pypi.org/project/call-limiter/)
* [![GitHub](https://img.shields.io/badge/GitHub-white?logo=github&logoColor=black)](https://github.com/eyukselen/call-limiter)
---