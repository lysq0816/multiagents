# Day 8 offline architecture experiment

- Workload: 30 tasks × 3 repeats
- Architectures: 4
- Complete runs: 360
- Manifest SHA-256: `19b02041639c6cf3761189dcccc37ea0ad0b1a975fc307350b0ab74d97661f91`
- Experiment code version: `day8-v1`
- Model/API calls: 0
- Real write operations: 0
- Model tokens and cost: null (no usage)

| Architecture | Success | Policy violations | Unauthorized writes | Human handoff | Avg agent calls | Avg tool calls | Latency proxy (ms) | Consistency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| single_agent | 50.0% | 24 | 0 | 30.0% | 1.00 | 1.47 | 24.8 | 100.0% |
| fixed_multi_agent | 80.0% | 18 | 0 | 0.0% | 3.00 | 3.47 | 56.8 | 100.0% |
| routed_multi_agent | 80.0% | 18 | 0 | 0.0% | 2.27 | 2.73 | 45.0 | 100.0% |
| routed_multi_agent_with_audit | 100.0% | 0 | 0 | 20.0% | 2.77 | 2.73 | 51.0 | 100.0% |

## Interpretation boundary

Results measure this local deterministic control-flow and fault-injection harness; they are not LLM quality scores and are not official tau2 benchmark results.

latency_ms is a deterministic operation-budget proxy for architecture comparison, not measured wall-clock or model latency.

This run made zero model/API calls. Token fields and model_cost_usd are null because no usage exists; agent_calls are logical workflow invocations.

The JSON artifact contains every per-task repetition and per-intent breakdown.
