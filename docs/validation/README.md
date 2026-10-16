# Validation evidence

- `tests.xml`: pytest integration-test results from the final build.
- `demo-evaluation.json`: eight deterministic golden scenarios through the real graph and MCP server. This is not a model-quality benchmark.
- `model-smoke.json`: actual Qwen3 1.7B output, measured runtime and reported token usage. The test stops at human approval and creates no order.
- `raw-sdk.txt`: actual read-only raw SDK tool-loop output.
- Screenshots: local purchasing UI with model mode and approval/receipt evidence.

The test suite verifies business-effect idempotency, policy checks, revisions, durable interrupts, restart, and independent checkpoint branches. One local-model smoke test does not establish general accuracy; the displayed recommendation facts are computed from verified catalog fields.

Final verification: 15 integration tests passed in 7.26 seconds; deterministic evaluation 8/8; real Qwen3 smoke test 6.98 seconds with no order created. Browser verification separately created a single simulated order after human confirmation and restored it after restarting the application.
