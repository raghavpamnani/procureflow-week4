# ProcureFlow: two-minute demo script

Target length: approximately two minutes at a natural speaking pace. Screen actions are directions for the presenter, not spoken narration. This is a recording script, not a recorded video.

## Preparation

Follow [DEMO.md](DEMO.md) for the fresh workspace and sample inputs. Use the deterministic demo mode for predictable screenshots and timing, and explicitly label it. Keep `docs/validation/model-smoke.json` open to show separately that actual Qwen3 local inference was verified. Do not imply the deterministic demo is a live model response.

## 0:00–0:15 — The problem

**Screen:** Purchasing desk; show the complete brief.

**Say:**

“ProcureFlow is a local purchasing assistant built for Week Four. It turns an equipment request into a supplier comparison and an auditable purchase recommendation. A human makes the final decision, and all purchases in this demonstration are simulated.”

## 0:15–0:35 — Specialists and MCP

**Screen:** Submit the default request with timeout recovery enabled. Show the activity trail.

**Say:**

“Here, we need ten developer laptops within nine lakh rupees. LangGraph coordinates the requirements analyst, supplier tools, and recommendation specialist. The tools run in a separate MCP server. This supplier call fails once, then recovers through a bounded retry.”

## 0:35–0:55 — Evidence and approval

**Screen:** Supplier table, recommendation and disabled execution until review.

**Say:**

“The cheapest supplier is rejected because it fails approval and warranty rules. Eligible alternatives meet our specifications, stock, delivery, and budget constraints. These checks run in code. The workflow now pauses with the exact proposal saved, rather than creating an order automatically.”

## 0:55–1:15 — Durable memory

**Screen:** Stop and restart the same server command, then reload the page.

**Say:**

“SQLite stores the graph checkpoints and pending human review. I can restart the application and return to the same proposal. Recent discussion stays available while older turns are summarized. The structured purchase requirements remain authoritative throughout the workflow.”

## 1:15–1:35 — Human revision

**Screen:** Revise brief; select Performance & warranty; submit the revised brief.

**Say:**

“I can approve, reject, or revise the request. Choosing performance and warranty produces a fresh recommendation, with its price and tradeoffs visible. Every revision invalidates the previous approval, so an old confirmation cannot authorize a changed purchase.”

## 1:35–1:50 — Execute once

**Screen:** Approve; confirm the displayed total; show the order receipt.

**Say:**

“After confirmation, the MCP order tool checks approval, current quote terms, budget, and stock again. A transaction creates one order. Repeating the same approved request returns its original receipt instead of purchasing twice.”

## 1:50–2:00 — Close with proof

**Screen:** Checkpoint selector, then validation evidence or repository README.

**Say:**

“Checkpoint branches let us compare alternatives with fresh approvals. The project also includes real local Qwen3 verification, fifteen passing tests, and eight deterministic purchasing scenarios. The repository contains setup instructions, architecture, and validation evidence.”

## Presenter's accuracy notes

- Demo mode uses deterministic decisions; Ollama mode uses local model inference. State which one is on screen.
- In the recorded demo, actual supplier names, price totals and timing must match what the app displays.
- Time travel does not reverse an already-created order; an alternative branch is a new request with a separate approval.
- No real money, email or external order is involved.
- If setup or restart takes longer than the slot, prepare the terminal commands before recording or edit out idle time transparently.
