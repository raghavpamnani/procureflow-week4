# Two-minute recording script

Use actual local-model mode for this walkthrough. This is a script, not a recorded video. See DEMO.md for preparation. Narration is approximately 250 words; rehearse with the actual screen and trim pauses to fit two minutes.

| Time | Screen action | Narration |
| --- | --- | --- |
| 0:00–0:15 | Show purchasing desk and local-model badge | “ProcureFlow turns a purchasing request into a checked recommendation and a human-approved order. It combines LangChain, LangGraph, a local Qwen model, SQLite, and MCP. Every supplier and purchase here is simulated.” |
| 0:15–0:35 | Signed in as requester, submit ten laptops, 32 GB RAM, nine lakh budget | “I’m requesting ten developer laptops within nine lakh rupees. A supervisor coordinates the specialist workflow. The supplier agent uses native tool calls to retrieve catalog and budget evidence from a separate MCP server. The activity trail records each step and bounded retry.” |
| 0:35–0:55 | Show supplier exclusions, recommendation, tool evidence | “Code checks specifications, warranty, delivery, stock, and budget. The cheapest offer fails policy. The recommendation explains an eligible alternative using verified prices. The model only receives read tools; it cannot create an order. My requester account cannot approve its own purchase.” |
| 0:55–1:15 | Restart same workspace; reload pending proposal | “The workflow pauses at a persistent human-review checkpoint. After restarting, the same proposal and fingerprint return. SQLite also preserves account sessions. Nothing has been purchased while we wait for an independent approver.” |
| 1:15–1:35 | Submit a prepared revision, show memory evidence | “A requester can revise the brief. A changed proposal needs fresh approval. Older discussion becomes structured semantic memory: preferences, decisions, and open questions. Recent messages remain available, while validated requirements stay authoritative.” |
| 1:35–1:50 | Sign in as approver; review and confirm; show receipt | “Now an independent approver confirms the proposal. The executor checks its fingerprint and current business rules again. One transaction creates one order; retrying returns the original receipt, including the approver’s identity.” |
| 1:50–2:00 | Show validation reports and green GitHub checks | “The repository includes automated tests, seven passing real-model scenarios, and Docker verification. It also tests recovery after a crash immediately following order creation. Setup, architecture, and security limitations are documented.” |

Only say the final Docker verification claim after the container job is green. Match supplier names and totals to the actual run. Edit out idle startup/inference time with a visible cut if necessary. Do not show account passwords or private files.
