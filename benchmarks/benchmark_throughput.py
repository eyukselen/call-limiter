from time import perf_counter, sleep
import time
import random
from call_limiter import CallLimiter
# from archive.limiter_archive import CallLimiter, CallLimiterV4


def unlimited_tester(func_to_limit, total_calls, label):
    start_time = perf_counter()
    for x in range(total_calls):
        func_to_limit()
    end_time = perf_counter()
    duration = end_time - start_time
    return {"label": label,
            "total_calls": total_calls,
            "calls_per_period": None,
            "period": None,
            "Burst": None,
            "elapsed_time": duration,
            "expected_time": None
            }


def limiter_tester(func_to_limit, call_limiter, calls_per_period, period, allow_burst, total_calls, label):
    limiter = call_limiter(calls_per_period, period, allow_burst)
    limited_func = limiter(func_to_limit)

    start_time = perf_counter()
    for x in range(total_calls):
        limited_func()
    end_time = perf_counter()
    duration = end_time - start_time
    return {"label": label,
            "total_calls": total_calls,
            "calls_per_period": calls_per_period,
            "period": period,
            "Burst": allow_burst,
            "elapsed_time": duration,
            "expected_time": (total_calls / calls_per_period) - period if allow_burst else (total_calls / calls_per_period),
            }

def _worker_cpu():
    dummy = 0
    for x in range(10_000):
        dummy += 1

def _worker_network():
    time.sleep(random.uniform(0.01, 0.1))


def benchmark_throughput():
    all_stats = []

    res = limiter_tester(_worker_cpu, CallLimiter, 10, 1, True, 60, "burst_cpu")
    all_stats.append(res)
    res = limiter_tester(_worker_cpu, CallLimiter, 10, 1, False, 60, "drip_cpu")
    all_stats.append(res)

    res = limiter_tester(_worker_network, CallLimiter, 10, 1, True, 60, "burst_network")
    all_stats.append(res)
    res = limiter_tester(_worker_network, CallLimiter, 10, 1, False, 60, "drip_network")
    all_stats.append(res)

    # res = unlimited_tester(_worker_cpu, 60, "raw_network")
    # all_stats.append(res)
    # res = unlimited_tester(_worker_network, 60, "raw_cpu")
    # all_stats.append(res)

    return all_stats

if __name__ == "__main__":
    all_stats = benchmark_throughput()
    res = benchmark_throughput()

    for item in res:
        print(item)
