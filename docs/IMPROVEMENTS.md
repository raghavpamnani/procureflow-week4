# Evaluation-focused improvements (v0.2)

These changes address identified weaknesses, not a promise of an official score.

| Area | Improvement | Evidence |
|---|---|---|
| Native LLM tool calling | The main supplier worker binds discovered read-only MCP schemas; the model selects calls, observes outputs, and continues within five iterations | Native-tool traces and local-model evaluation |
| Tool permissions | Supplier sees only search_catalog/get_budget; write tool stays behind independent human approval | Forbidden-tool test, MCP commit checks |
| Memory | Typed preferences/decisions/unresolved_questions; real model semantically merges older discussion; recent exchanges and authoritative request remain separate | Semantic summary tests and real revision evaluation |
| Auth/RBAC | Operator-provisioned accounts, scrypt hashes, persistent opaque sessions, immutable ownership, independent approver | API/CLI role and session tests |
| Abuse controls | Persistent login/write rate limits, four-job queue ceiling, same-origin writes, trusted hosts | Rate-limit and cross-origin tests |
| Reliability | Actual asynchronous read deadline with three attempts; independent-process crash after order commit before checkpoint | Deadline and crash-recovery tests |
| Packaging | Non-root Docker image, healthcheck, persistent data volume, optional internal Ollama service | Separate container CI job |
| Model evaluation | Constraint variants, infeasible requests, instruction injection and semantic-memory revision, with explicit success/failure reporting | Real-model evaluation JSON; no fake precision claim |
| Demonstration | Updated timed script and screen actions include role separation and native tool evidence | VIDEO_SCRIPT.md / DEMO.md |

The deterministic scenario evaluation remains useful for reproducibility but is not presented as an LLM accuracy benchmark. Local-model measurements and container CI results must be reported independently. A two-minute script is not an actual recorded video.
