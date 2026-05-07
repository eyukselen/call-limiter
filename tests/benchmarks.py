from time import perf_counter, sleep
import time
import threading
from functools import wraps
from typing import Callable
import random
from archive.limiter_archive import CallLimiterV3, CallLimiterV4


def unlimited_tester(func_to_limit, total_calls, label):
    start_time = perf_counter()
    for x in range(total_calls):
        func_to_limit()
    end_time = perf_counter()
    duration = end_time - start_time
    return {"label": label,
            "total_calls": total_calls,
            "calls": None,
            "period": None,
            "duration": duration,
            "expected_calls": None,
            "actual_calls": total_calls / duration
            }


def limiter_tester(func_to_limit, call_limiter, calls, period, allow_burst, total_calls, label):
    limiter = call_limiter(calls, period, allow_burst)
    limited_func = limiter(func_to_limit)

    start_time = perf_counter()
    for x in range(total_calls):
        limited_func()
    end_time = perf_counter()
    duration = end_time - start_time
    return {"label": label,
            "total_calls": total_calls,
            "calls": calls,
            "period": period,
            "duration": duration,
            "expected_calls": calls/period,
            "actual_calls": total_calls / (duration + period if allow_burst else duration) # post-fence
            }

def _worker():
    dummy = 0
    for x in range(10_000):
        dummy += 1

def _worker_network():
    time.sleep(random.uniform(0.01, 0.1))




all_stats = []

res = limiter_tester(_worker, CallLimiterV3, 10, 1, True, 60, "CallLimiterV3_burst_cpu")
all_stats.append(res)
res = limiter_tester(_worker, CallLimiterV3, 10, 1, False, 60, "CallLimiterV3_drip_cpu")
all_stats.append(res)

res = limiter_tester(_worker, CallLimiterV4, 10, 1, True, 60, "CallLimiterV4_Final_burst_cpu")
all_stats.append(res)
res = limiter_tester(_worker, CallLimiterV4, 10, 1, False, 60, "CallLimiterV4_Final_drip_cpu")
all_stats.append(res)


res = limiter_tester(_worker_network, CallLimiterV3, 10, 1, True, 60, "CallLimiterV3_burst_network")
all_stats.append(res)
res = limiter_tester(_worker_network, CallLimiterV3, 10, 1, False, 60, "CallLimiterV3_drip_network")
all_stats.append(res)

res = limiter_tester(_worker_network, CallLimiterV4, 10, 1, True, 60, "CallLimiterV4_Final_burst_network")
all_stats.append(res)
res = limiter_tester(_worker_network, CallLimiterV4, 10, 1, False, 60, "CallLimiterV4_Final_drip_network")
all_stats.append(res)


res = unlimited_tester(_worker, 60, "Raw")
all_stats.append(res)

for item in all_stats:
    print(item)
