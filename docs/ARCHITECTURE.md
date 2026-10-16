# ProcureFlow architecture

## Why this project

A purchasing request has a concrete outcome, several independent sources of evidence, and a legitimate approval boundary. A three-agent design is enough: supervisor, requirements analyst, and recommendation specialist. Catalog retrieval and policy checking are deterministic workers; calling them "agents" would overstate their autonomy. The executor is a restricted write path, never a model-owned tool.

This is a local single-user teaching application, not an ERP or payment processor. All six products and suppliers are fictional. Prices are integer INR inclusive of GST. No real bookings, emails, payments, or purchases occur.

```mermaid
flowchart TD
    A[Structured purchase brief] --> I[Intake / validate]
    I --> S[Supervisor]
    S -->|requirements missing| R[Requirements analyst]
    S -->|quotes missing| Q[Supplier worker / MCP]
    R --> S
    Q --> S
    S -->|evidence ready| P[Policy checker / MCP]
    P --> S
    S -->|checks ready| C[Recommendation specialist]
    C --> M[Compact active memory / save exact proposal]
    M --> H{Durable human interrupt}
    H -->|Revise, max 4| I
    H -->|Reject| Z[End]
    H -->|Approve matching hash| E[Order executor / MCP]
    E --> T[Transactional recheck + idempotent insert]
    T --> Z
    DB[(SQLite checkpoints)] -. saves every superstep .-> S
    DB -. persists pending interrupt .-> H
```

## Components

- `api.py`: FastAPI endpoints and background jobs. Frontend polls saved graph state for progress. Jobs are in-process; the durable graph, rather than the job object, survives restart.
- `workflow.py`: typed `StateGraph`, conditional routes, explicit cycles, audit reducer and `interrupt()` / `Command(resume=...)`.
- `agents.py`: LangChain `ChatOllama` structured outputs with bounded worker inputs. Recommendation reason codes are verified against eligible quotes; prices, delivery and tradeoff text are rendered from trusted fields. Singleton routing is deterministic to avoid redundant model calls. Demo mode is an explicitly selected deterministic implementation. There is no silent fallback on model failure.
- `tools.py`: official MCP client; `initialize`, `list_tools`, then `call_tool` over stdio to a separate Python process. Up to three attempts for explicitly retryable tool results.
- `mcp_server.py`: official FastMCP server; exposes four tools with discovered JSON schemas.
- `store.py`: independent business SQLite connection per operation, WAL, transaction-bound stock/budget checks and idempotent writes.
- `memory.py`: extractive summary of older turns plus four recent exchanges. Structured requirements remain authoritative. Full history remains in checkpoints.

## State schema

| Field | Purpose / update rule |
|---|---|
| `request_id`, `mode` | Stable workflow identity and explicit execution mode |
| `request` | Validated hard constraints; replaced only by a validated human revision |
| `assessment` | Requirements analysis |
| `quotes`, `policy` | Catalog evidence and deterministic per-quote checks |
| `recommendation`, `proposal`, `proposal_hash` | Explanation, exact action payload, SHA-256 fingerprint |
| `revision` | Maximum four revision cycles |
| `audit` | Append-only list reducer, `operator.add`; nodes return dictionary updates |
| `recent_turns`, `memory_summary` | Bounded working context; older notes condensed extractively |
| `context_bytes`, `model_usage` | Measured bytes and reported model token usage, kept distinct |
| `order` | Confirmed local order receipt |
| `parent` | Source request and checkpoint for an alternative branch |

## MCP boundaries

| Tool | Access | Caller |
|---|---|---|
| `search_catalog` | Read; optional once-per-request/revision simulated failure | Supplier worker |
| `get_budget` | Read | Budget inspection / integration clients |
| `evaluate_quotes` | Read; reloads trusted catalog to avoid supplied-price spoofing | Policy checker |
| `create_purchase_order` | Write; independently requires stored approval | Executor after human interrupt |

The model sees task data, not direct access to the write tool or approval ledger. The application owns delegation/tool access. Discovery does not automatically grant every worker every tool.

## Approval and exactly-once business effect

1. Persist the complete proposal and hash with approval cleared.
2. Checkpoint a dynamic interrupt containing the exact proposal.
3. Validate the review payload and hash before resuming.
4. Persist approval for that request/hash after the interrupt returns.
5. Executor calls the MCP write tool. Inside `BEGIN IMMEDIATE`, check existing order, approval, current supplier terms, specs, budget and stock; insert one order and decrement stock atomically.
6. A unique `request_id` prevents duplicate orders. Replay with the same hash returns the original receipt; a different hash is rejected.

A model-generated "approved" string has no authority. A restart between commit and graph checkpoint can safely re-run the executor. An actual remote ERP would also need to honor an idempotency key; this local guarantee does not magically extend to external services.

## Checkpoints and time travel

SQLite checkpoints store intermediate supersteps and pending interrupts. Resume uses the same `thread_id`. The UI lists historical checkpoints. Branching first restores the selected snapshot's brief into the edit form. It preserves bounded working memory from that point and seeds a new thread with `aupdate_state`, resetting all derived outputs, orders and approvals, then recalculates with the edited brief. Source provenance and unaffected earlier requests remain visible.

This is a conservative checkpoint-based alternative branch, not an undo of external actions. A prior order stays committed. Each new branch requires independent approval and consumes its own stock/budget if eventually approved.

## Context and iteration budgets

- Four revisions maximum; graph recursion limit 80 per invocation.
- MCP tool attempts: three; 20-second read timeout per call.
- Model request timeout: 90 seconds; output cap: 700 tokens; configured context: 8192.
- Worker input including schema/system/task is capped at 6500 UTF-8 bytes. This is a conservative guard for the tested model, not an exact tokenizer count. Ollama-reported usage is recorded separately.
- Recent conversation: four turns and a 6000-byte serialized working-memory ceiling. Summary is bounded to 1800 UTF-8 bytes. Hard constraints are stored separately and are never recovered from a potentially lossy summary.
- Full checkpoint history is intentionally retained for audit and time travel; active-context pruning is not database retention management.

## Operational limits

One Uvicorn worker on localhost only. No user accounts or RBAC. SQLite business files are protected by the local filesystem, not application-level encryption. Use trusted local inputs; model explanations are advisory and can be wrong. Formal checks and totals are deterministic. Multiple app processes sharing a home are unsupported despite transactional order insertion. Human reviews have no expiry; commit-time revalidation catches changed terms. No automatic purchase is allowed when no quote meets every constraint.
