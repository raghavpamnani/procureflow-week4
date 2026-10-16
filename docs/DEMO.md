# Two-minute walkthrough

Use demo mode for predictable timing. Clearly state that this shows the actual LangGraph/MCP/persistence workflow with deterministic decisions; show a separate real-model run to demonstrate local inference. Do not present demo text as LLM output.

## Before recording

Start from a fresh home without deleting earlier work:

```sh
PROCUREFLOW_HOME=.runtime/recording-01 ./scripts/run.sh
```

Use ten laptops, 32 GB RAM, 512 GB storage, INR 900000 budget, 14-day delivery, Best value. Leave the timeout checkbox checked.

## Narration

- **0:00-0:15**: "ProcureFlow turns a purchasing brief into an auditable recommendation. It runs locally with LangGraph, SQLite and MCP. No real purchases occur."
- **0:15-0:35**: Submit. Point to supervisor delegation, the failed first catalog call and successful retry. Point out the cheapest quote is disqualified by supplier/warranty policy.
- **0:35-0:55**: Show Orbit at INR 810000; no purchase order exists. Explain the independent approval gate.
- **0:55-1:15**: Stop the server with Ctrl-C. Restart the exact same command. Reload the browser and show the same pending proposal and fingerprint.
- **1:15-1:35**: Click Revise brief. Change Optimize for to Performance & warranty. Click Submit revised brief. The sample deterministic ranking chooses Cedar at INR 870000 with 1 TB and a three-year warranty.
- **1:35-1:50**: Approve. Show one order and the reduced department budget. Explain commit-time stock/policy checks and the unique request key.
- **1:50-2:00**: Show the checkpoint selector. Explain a branch can explore an alternative without rewriting the prior order; it requires a fresh approval.

## Optional extended proof

- Set RAM to 64 GB: no quote is eligible; approval stays disabled.
- Make four revisions: older discussion becomes a compact summary; hard requirements remain intact.
- Create an alternative branch with a shorter delivery deadline: it gets its own ID and review.
- Show `docs/validation/model-smoke.json` after running the actual local-model verification.

## Recording status

This document is the script, not a Loom link. The public source repository includes this script. The actual video still needs to be recorded and its link added before assignment submission.
