# ProcureFlow · Week 4

**Purchasing, with proof.** A local multi-agent purchasing assistant with model-selected MCP tools, semantic memory, durable human review, and independent requester/approver accounts. All suppliers, prices and purchase orders are fictional local simulations.

![Purchasing desk](docs/validation/desk.jpg)

A requester defines ten developer laptops, at least 32 GB RAM, a total budget of INR 900000 and delivery within fourteen days. Specialists retrieve quotes, enforce policy in code, and recommend an eligible option. An independent approver reviews the exact purchase order before execution. Restarts preserve pending approval; retries cannot create a duplicate order.

## Quick start

Python 3.11+ is required; Python 3.12 is the tested version.

```sh
./scripts/setup.sh
./scripts/python.sh -m procureflow.accounts bootstrap-demo
./scripts/run.sh
```

`bootstrap-demo` creates separate requester and approver accounts with random passwords in `.runtime/demo-accounts.txt` (owner-only file permissions). Read that private file locally; never commit it or show it in a video. There are no published default passwords. Bootstrap refuses to overwrite existing accounts.

Open http://127.0.0.1:8040 and sign in as requester. The default demo mode uses deterministic decisions while exercising the real graph, MCP process, persistence, roles, and approval controls. Its badge explicitly says **DEMO MODE - NO LLM**.

To choose your own passwords instead:

```sh
./scripts/python.sh -m procureflow.accounts create-user --username buyer --role requester
./scripts/python.sh -m procureflow.accounts create-user --username reviewer --role approver
```

On macOS the Python environment lives in `~/Library/Caches/ProcureFlow/venv`, outside synced Documents. Linux uses `.venv`. `PROCUREFLOW_VENV` can override that choice. Scripts anchor their working directory to the project. Account data, business data and checkpoints live in `PROCUREFLOW_HOME` (default `.runtime`); use the same home on restart.

## Actual local open model

Install [Ollama](https://ollama.com/download), start its local server and pull Qwen3:

```sh
ollama pull qwen3:1.7b
PROCUREFLOW_MODE=ollama ./scripts/run.sh
```

For the cache-based runtime prepared on this development Mac:

```sh
# Terminal 1: model server on localhost:11435; cloud inference disabled
./scripts/serve_local_model.sh

# Once per model installation, in another terminal
OLLAMA_HOST=http://127.0.0.1:11435 ollama pull qwen3:1.7b

# Accounts for the same workspace used by run_local.sh
./scripts/python.sh -m procureflow.accounts --home .runtime/local-model-demo bootstrap-demo

# Terminal 2: app with real local inference
./scripts/run_local.sh
```

If the cached CLI is not on PATH, use `~/Library/Caches/ProcureFlow/ollama/ollama` in place of `ollama`. Bootstrap is unnecessary if accounts already exist. On this Mac its private account file is `.runtime/local-model-demo/demo-accounts.txt`.

The model runtime and weights are in `~/Library/Caches/ProcureFlow/ollama` and `~/Library/Caches/ProcureFlow/models`. This prevents cloud-file eviction of weights under Documents. They are not in the public repository. A compact model is used for the 8 GB Mac; larger models can be configured on suitable hardware. Model failures never silently switch to demo mode.

LangChain provides model integration and native tool binding. LangGraph controls state, cycles, checkpointing, interrupts and branches. The official MCP SDK provides real discovery and calls over stdio. No Deep Agents abstraction or paid model API is required.

## Workflow and controls

1. **Requester** submits a structured brief and ranking preferences.
2. **Supervisor** routes ready tasks; specialists receive bounded contexts.
3. **Supplier agent** uses native model tool calls to select `search_catalog` and `get_budget`, observe results, and finish within five iterations. It cannot access the order tool. Demo mode explicitly scripts the same loop.
4. **Policy worker** verifies supplier approval, warranty, specifications, stock, delivery and both budgets using current catalog data.
5. **Recommendation agent** selects an eligible ID and verified reason codes. Prices and tradeoffs are rendered from trusted fields, rather than accepting model-generated arithmetic.
6. **Requester** can revise up to four times. Old discussion becomes typed semantic memory in model mode; demo mode stores deterministic structured records. Hard constraints remain separate.
7. **Independent approver** signs in to approve/reject. A requester cannot approve their own request. Approval binds the exact proposal hash and identity.
8. **MCP executor** rechecks current terms, budget, stock and reviewer identity inside a transaction. A unique request key gives one business effect even if execution is repeated after a crash.

The interface provides a decision report, native-tool/memory evidence, order history and historical checkpoint selection. Branching restores the earlier brief and memory into a new request and requires fresh approval. It never reverses an existing order.

Old unowned requests from pre-authentication versions remain visible only to approvers and cannot receive new authenticated approval; create a new brief.

## Restart and CLI

Stop and restart the exact same server command, then reopen the request. SQLite stores sessions, state and pending approval. A request that failed during inference has a retry control. Research retries belong to the requester; order-execution retries belong to an independent approver.

The CLI also requires account credentials:

```sh
./scripts/python.sh -m procureflow.cli --username buyer new --timeout
./scripts/python.sh -m procureflow.cli --username buyer show REQUEST_ID
./scripts/python.sh -m procureflow.cli --username reviewer approve REQUEST_ID
```

Passwords are prompted, not passed in command arguments. Review the order and type APPROVE for the local simulated action. Use the same `PROCUREFLOW_HOME` and model settings as the application.

## Verification

```sh
./scripts/python.sh -m pytest -q
./scripts/python.sh -m ruff check procureflow scripts tests
./scripts/python.sh scripts/evaluate.py
OLLAMA_HOST=http://127.0.0.1:11435 ./scripts/python.sh scripts/verify_model.py
OLLAMA_HOST=http://127.0.0.1:11435 ./scripts/python.sh scripts/evaluate_model.py
```

Tests exercise real MCP subprocesses and SQLite checkpoints, auth roles and isolation, login limits, actual asynchronous deadlines, a process crash after commit but before checkpoint, semantic-memory structure, and forbidden agent tool calls. The real-model evaluation covers several constraint cases, instruction injection and semantic memory after revision. It creates no orders. Small evaluation sets are not general model-accuracy guarantees.

For the separate Day 16 raw SDK learning example:

```sh
OLLAMA_HOST=http://127.0.0.1:11435 ./scripts/python.sh scripts/react_basics.py
```

## Docker

```sh
docker compose up --build -d
docker compose exec app python -m procureflow.accounts --home /data bootstrap-demo
```

See [Docker instructions](docs/DOCKER.md) for private credentials, persisted review across container restarts, and the optional local-model profile. GitHub Actions separately builds the non-root image and tests the approval workflow through a container restart. Docker is not installed on the development Mac; container evidence comes from CI.

## Documentation and submission

- [Architecture and state schema](docs/ARCHITECTURE.md)
- [Security and role matrix](docs/SECURITY.md)
- [Evaluation-focused improvements](docs/IMPROVEMENTS.md)
- [Day 16-20 mapping](docs/CURRICULUM.md)
- [Two-minute video script](docs/VIDEO_SCRIPT.md)
- [Recording setup and actions](docs/DEMO.md)
- [Validation evidence](docs/validation/)
- [Submission checklist](docs/SUBMISSION.md)

Public repository: https://github.com/raghavpamnani/procureflow-week4

The actual recorded video and final assignment-form submission remain separate deliverables.

## Scope and references

Local multi-account demo, one app worker, no real supplier/payment service, no organization tenancy. Accounts and roles protect application operations; a local operator with arbitrary code/filesystem access remains trusted. See [security limits](docs/SECURITY.md). Keep runtime databases, credentials and model weights out of Git.

References: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [ChatOllama tools](https://docs.langchain.com/oss/python/integrations/chat/ollama), [official MCP SDK](https://github.com/modelcontextprotocol/python-sdk).
