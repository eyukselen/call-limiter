# Benchmarks for Throughput
| label         | total_calls | calls_per_period | period | Burst | elapsed_time      | expected_time |
| ------------- | ----------- | ---------------- | ------ | ----- | ----------------- | ------------- |
| burst_cpu     | 60          | 10               | 1      | 1     | 5.001779255049769 | 5.0           |
| drip_cpu      | 60          | 10               | 1      | 0     | 5.900217906979378 | 6.0           |
| burst_network | 60          | 10               | 1      | 1     | 5.516547188977711 | 5.0           |
| drip_network  | 60          | 10               | 1      | 0     | 5.992925723956432 | 6.0           |

> all values for durations are in seconds
