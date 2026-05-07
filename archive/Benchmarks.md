# Benchmarks for new improvements

| Mode   | Scenario |V3 Duration | V4_Final Duration | Difference | Winner               |
|--------|-----------|------------|------------------|------------|----------------------|
| Burst  | CPU	      | 5.050      | 5.050s	          | 0.000s	   | Tie                  |
| Drip	  | CPU	      | 5.949s     | 5.948s	          | -0.001s	   | Tie (Noise)          |
| Burst  | Network	  | 5.109s     | 5.092s	          | -0.017s	   | V4_Final (Tiny edge) |
| Drip	  | Network	  | 6.328s     | 6.311s	          | -0.017s	   | V4_Final (Tiny edge) |

V4_Final is still experimental but performing slightly better than V3.
tested for network based idle time calls and cpu bound calls.



