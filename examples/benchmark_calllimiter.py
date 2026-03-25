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

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from call_limiter import CallLimiter


def benchmark_precision(calls_per_sec, total_calls):
    """Measure limiter precision at a given rate and return results."""
    period = 1.0
    expected_interval = period / calls_per_sec

    limiter = CallLimiter(calls=calls_per_sec, period=period, allow_burst=False)

    timestamps = []

    @limiter
    def record():
        timestamps.append(time.perf_counter())

    start = time.perf_counter()
    for _ in range(total_calls):
        record()
    elapsed = time.perf_counter() - start

    gaps = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]

    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)
    min_gap = min(gaps)
    max_gap = max(gaps)
    drift_per_call = avg_gap - expected_interval
    total_drift = drift_per_call * len(gaps)

    tolerance = expected_interval * 0.10
    accurate = sum(1 for g in gaps if abs(g - expected_interval) <= tolerance)
    accuracy_pct = accurate / len(gaps) * 100

    expected_time = (total_calls - 1) * expected_interval
    time_error = elapsed - expected_time

    return {
        "rate": calls_per_sec,
        "total_calls": total_calls,
        "expected_interval": expected_interval,
        "avg_gap": avg_gap,
        "min_gap": min_gap,
        "max_gap": max_gap,
        "drift_per_call": drift_per_call,
        "total_drift": total_drift,
        "accuracy_pct": accuracy_pct,
        "accurate": accurate,
        "gap_count": len(gaps),
        "elapsed": elapsed,
        "expected_time": expected_time,
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


def print_summary(results):
    """Print a summary table of all results."""
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Rate':>10}  {'Calls':>8}  {'Avg Gap':>10}  {'Drift':>10}  {'Accuracy':>10}")
    print(f"  {'(calls/s)':>10}  {'':>8}  {'(ms)':>10}  {'(ms)':>10}  {'(±10%)':>10}")
    print("-" * 70)
    for r in results:
        print(
            f"  {r['rate']:>10,}  {r['total_calls']:>8,}  "
            f"{r['avg_gap'] * 1000:>10.3f}  "
            f"{r['total_drift'] * 1000:>10.1f}  "
            f"{r['accuracy_pct']:>9.1f}%"
        )
    print("-" * 70)
    print()


if __name__ == "__main__":
    rates = [5000, 10000, 20000, 50000, 100000, 200000]

    print()
    print("=" * 70)
    print("  CallLimiter Precision Benchmark (drip mode, 2 seconds per rate)")
    print("=" * 70)
    print()

    results = []
    for rate in rates:
        total = rate * 2
        print(f"--- {rate:,} calls/sec ({total:,} calls) ---")
        r = benchmark_precision(rate, total_calls=total)
        if r:
            print_detail(r)
            results.append(r)

    if results:
        print_summary(results)
