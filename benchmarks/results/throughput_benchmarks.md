# Benchmarks for Throughput
| label         | total_calls | calls_per_period | period | Burst | elapsed_time      | expected_time |
| ------------- | ----------- | ---------------- | ------ | ----- | ----------------- | ------------- |
| burst_cpu     | 60          | 10               | 1      | 1     | 5.005426641961094 | 5.0           |
| drip_cpu      | 60          | 10               | 1      | 0     | 5.900556498032529 | 6.0           |
| burst_network | 60          | 10               | 1      | 1     | 5.475086208956782 | 5.0           |
| drip_network  | 60          | 10               | 1      | 0     | 5.99076996895019  | 6.0           |

> all values for durations are in seconds
