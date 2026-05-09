"""
CallLimiter Precision Benchmark
===============================
This script measures the timing accuracy of CallLimiter in drip mode
(allow_burst=False) across a range of call rates.

Each rate is tested for 2 full seconds of sustained calls.
A call is considered "accurate" if its interval is within ±10% of the
expected interval for that rate.

Run:
    python examples/benchmark_calllimiter.py
"""

import time
import sys
import os
from typing import Any, Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from call_limiter import CallLimiter


def benchmark_precision(calls_per_sec, period_seconds,  total_calls, allow_burst):
    """Measure limiter precision at a given rate and return results."""
    period = period_seconds
    burst_mode = allow_burst

    timestamps = []
# region execution
    limiter = CallLimiter(calls=calls_per_sec, period=period, allow_burst=burst_mode)

    @limiter
    def record():
        timestamps.append(time.perf_counter())

    start_time = time.perf_counter()
    for _ in range(total_calls):
        record()

    elapsed = time.perf_counter() - start_time
# endregion

# region calculate gaps for drifting
    expected_start = 0.0
    expected_calls_per_period = calls_per_sec

    if burst_mode:
        expected_timestamps = [
            start_time + (i // expected_calls_per_period) * period
            for i in range(total_calls)
        ]
    else:
        expected_timestamps = [start_time + i * (period / expected_calls_per_period)
                               for i in range(total_calls)]
    noised_drift = []
    actual_drift = []
    for x in range(total_calls):
        drift = timestamps[x] - expected_timestamps[x]
        noised_drift.append(drift)
        if burst_mode:
            if x % expected_calls_per_period == 0:
                actual_drift.append(drift)
        else:
            actual_drift.append(drift)

    # noised_total_drift = sum(noised_drift)
    # noised_avg_drift = sum(noised_drift) / len(noised_drift)
    # noised_max_drift = max(noised_drift)
    # noised_min_drift = min(noised_drift)
    # actual_total_drift = sum(actual_drift)
    # actual_avg_drift = sum(actual_drift) / len(actual_drift)
    actual_max_drift = max(actual_drift)
    # actual_min_drift = min(actual_drift)


    if burst_mode:
        expected_duration = (total_calls  / calls_per_sec) - period
    else:
        expected_duration = (total_calls - 1) / calls_per_sec * period

    time_error = elapsed - expected_duration
    accuracy_pct = 100 * (1 - abs(time_error) / expected_duration)


    return {
        "rate": calls_per_sec, # given input
        "total_calls": total_calls, # given input
        "mode": "burst" if burst_mode else "drip",
        "expected_total_time": expected_duration,  # total duration expected
        "elapsed": elapsed, # execution duration
        "max_single_drift": actual_max_drift,
        "accuracy_pct": accuracy_pct,
        "time_error": time_error,
    }


def print_detail(r):
    """Print detailed results for a single rate."""
    print(f"  Target rate:       {r['rate']} calls/sec")
    print(f"  Expected interval: {r['expected_interval'] * 1000:.3f} ms")
    print(f"  Avg interval:      {r['avg_gap'] * 1000:.3f} ms")
    print(f"  Min interval:      {r['min_gap'] * 1000:.3f} ms")
    print(f"  Max interval:      {r['max_gap'] * 1000:.3f} ms")
    print(f"  Drift per call:    {r['drift_per_call'] * 1000:.3f} ms")
    print(f"  Total drift:       {r['total_drift'] * 1000:.1f} ms over {r['gap_count']} intervals")
    print(f"  Accuracy (±10%):   {r['accuracy_pct']:.1f}% ({r['accurate']}/{r['gap_count']} gaps)")
    print(f"  Total elapsed:     {r['elapsed']:.4f}s (expected {r['expected_time']:.4f}s, error {r['time_error'] * 1000:.1f}ms)")
    print()

def detail_report(r):
    detail = {"name": "precision benchmark",
              "Target rate":       f"{r['rate']} calls/sec",
              "Expected interval": f"{r['expected_interval'] * 1000:.3f} ms",
              "Avg interval":      f"{r['avg_gap'] * 1000:.3f} ms",
              "Min interval":      f"{r['min_gap'] * 1000:.3f} ms",
              "Max interval":      f"{r['max_gap'] * 1000:.3f} ms",
              "Drift per call":    f"{r['drift_per_call'] * 1000:.6f} ms",
              "Total drift":       f"{r['total_drift'] * 1000:.1f} ms over {r['gap_count']} intervals",
              "Accuracy":          f"{r['accuracy_pct']:.1f}% ({r['accurate']}/{r['gap_count']} gaps)",
              "Total elapsed":     f"{r['elapsed']:.4f}s (expected {r['expected_time']:.4f}s, error {r['time_error'] * 1000:.3f}ms)",
              }
    return detail
