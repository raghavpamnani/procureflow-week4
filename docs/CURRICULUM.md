# Week 4 requirement map

| Day | Requirement | Implementation | Verification |
|---|---|---|---|
| 16 | Reason/Act/Observe, raw SDK, bounded loops | `scripts/react_basics.py`; six-iteration Ollama tool loop | Run with real local model; read-only |
| 16 | Plan/execute and routing | Structured brief, supervisor routes to specialist tasks | Inspect saved audit and graph |
| 17 | State, reducers, conditional edges, cycles | `workflow.py`; typed state, audit reducer, revision branch | Revision and infeasible-request tests |
| 18 | SQLite checkpointing | `AsyncSqliteSaver`; stable `thread_id` | Separate CLI processes create and approve |
| 18 | Context pruning, token budgets | `memory.py`, bounded worker prompts, usage metadata | Four-revision compaction test; real-model smoke |
| 19 | Supervisor, bounded specialist contexts | Supervisor, requirements analyst, recommendation specialist | Audit and model usage records |
| 19 | MCP client/server, dynamic discovery | Official stdio client and FastMCP server | Real subprocess tools in integration tests |
| 20 | Interrupts and approve/reject/edit | Dynamic `interrupt`, validated `Command(resume=...)` | Approval, rejection, revision and stale-hash tests |
| 20 | Persistent human review | Durable interrupted state | Separate-process restart test |
| 20 | Time travel | Checkpoint selector, branch into new request | Branch test; independent approval enforced |
| Weekly | Automated retries | Three bounded attempts for explicit transient tool errors | Injected timeout audit |
| Weekly | Local open model | Ollama + Qwen3, LangChain adapter; no cloud inference required | `scripts/verify_model.py` |
| Weekly | Repository and documentation | Modular package, locked dependencies, architecture, usage, tests | `python -m pytest -q` |
| Weekly | Two-minute video | Recording script in `DEMO.md` | User records walkthrough; no completed video claimed |

The Day 20 exercise mentions `interrupt_before`. This app uses dynamic `interrupt()` for structured approve/reject/edit input. It preserves the intended pause-before-write behavior and also supports persisted review payloads. Official reference: https://docs.langchain.com/oss/python/langgraph/interrupts

Day 19 mentions SSE. This project uses stdio; it does not rely on legacy HTTP/SSE transport.
