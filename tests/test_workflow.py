import asyncio
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from procureflow.api import create_app
from procureflow.memory import MAX_CONTEXT_BYTES, compact
from procureflow.schemas import Decision, PurchaseRequest
from procureflow.service import Conflict, open_service
from procureflow.store import Store


def seed_client(client):
    auth = client.app.state.auth
    for role in ["requester", "approver"]:
        auth.create_user(role, "Test-password-12345", role)
    login_client(client, "requester")


def login_client(client, username):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "Test-password-12345"},
    )
    assert response.status_code == 200
    return response.json()["user"]


def run(coro):
    return asyncio.run(coro)


def test_real_mcp_restart_approval_and_idempotency(tmp_path):
    async def first():
        async with open_service(tmp_path, "demo") as s:
            assert set(s.tools.schemas) == {
                "search_catalog",
                "get_budget",
                "evaluate_quotes",
                "create_purchase_order",
            }
            state = await s.create(PurchaseRequest(simulate_timeout=True))
            assert state["status"] == "awaiting_approval"
            assert not s.store.orders()
            assert state["proposal"]["selected_id"] == "orbit-32"
            attempts = [
                t
                for e in state["audit"]
                for t in e.get("tools", [])
                if t["tool"] == "search_catalog"
            ]
            assert [x["ok"] for x in attempts] == [False, True]
            return state

    state = run(first())

    async def second():
        async with open_service(tmp_path, "demo") as s:
            restored = await s.get(state["request_id"])
            assert restored["pending"][0]["proposal_hash"] == state["proposal_hash"]
            d = Decision(action="approve", proposal_hash=state["proposal_hash"])
            out = await s.decide(state["request_id"], d)
            assert out["status"] == "completed"
            assert out["order"]["total_inr"] == 810000
            assert (await s.decide(state["request_id"], d))["order"] == out["order"]
            assert (
                await s.tools.call(
                    "create_purchase_order",
                    {
                        "request_id": state["request_id"],
                        "proposal_hash": state["proposal_hash"],
                    },
                )
                == out["order"]
            )
            assert len(s.store.orders()) == 1
            assert s.store.budget()["committed_inr"] == 810000
            assert (
                next(x for x in s.store.catalog() if x["id"] == "orbit-32")["stock"]
                == 10
            )

    run(second())


def test_true_separate_process_restart(tmp_path):
    from procureflow.auth import Auth

    auth = Auth(tmp_path)
    for role in ["requester", "approver"]:
        auth.create_user(role, "Test-password-12345", role)
    env = dict(os.environ, PROCUREFLOW_HOME=str(tmp_path), PROCUREFLOW_MODE="demo")
    create = subprocess.run(
        [
            sys.executable,
            "-m",
            "procureflow.cli",
            "--username",
            "requester",
            "new",
            "--timeout",
        ],
        input="Test-password-12345\n",
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    state = json.loads(create.stdout)
    approved = subprocess.run(
        [
            sys.executable,
            "-m",
            "procureflow.cli",
            "--username",
            "approver",
            "approve",
            state["request_id"],
        ],
        input="Test-password-12345\nAPPROVE\n",
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert '"status": "completed"' in approved.stdout
    assert len(Store(tmp_path).orders()) == 1


def test_no_eligible_and_rejection(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            a = await s.create(PurchaseRequest(min_ram_gb=64))
            assert not a["pending"][0]["can_approve"]
            with pytest.raises(Conflict):
                await s.decide(
                    a["request_id"],
                    Decision(action="approve", proposal_hash=a["proposal_hash"]),
                )
            out = await s.decide(
                a["request_id"],
                Decision(action="reject", proposal_hash=a["proposal_hash"]),
            )
            assert out["status"] == "rejected"
            assert not s.store.orders()

    run(scenario())


def test_revise_stale_approval_and_pruning(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            state = await s.create(PurchaseRequest())
            old = state["proposal_hash"]
            for i in range(4):
                req = PurchaseRequest(
                    priority="performance" if i % 2 == 0 else "value",
                    notes=f"Revision {i}: compare warranty carefully.",
                )
                state = await s.decide(
                    state["request_id"],
                    Decision(
                        action="revise",
                        proposal_hash=state["proposal_hash"],
                        revision=req,
                        note=f"Revision {i}",
                    ),
                )
            assert state["revision"] == 4
            assert state["memory_summary"]
            assert len(state["recent_turns"]) <= 4
            assert state["context_bytes"] <= MAX_CONTEXT_BYTES
            with pytest.raises(Conflict):
                await s.decide(
                    state["request_id"], Decision(action="approve", proposal_hash=old)
                )
            with pytest.raises(Conflict):
                await s.decide(
                    state["request_id"],
                    Decision(
                        action="revise",
                        proposal_hash=state["proposal_hash"],
                        revision=PurchaseRequest(),
                    ),
                )
            assert not s.store.orders()

    run(scenario())


def test_checkpoint_branch_clears_approval(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            a = await s.create(PurchaseRequest())
            history = await s.history(a["request_id"])
            checkpoint = next(x for x in history if x["next"] == ["approval"])
            b = await s.fork(
                a["request_id"],
                checkpoint["checkpoint_id"],
                PurchaseRequest(priority="performance"),
            )
            assert a["request_id"] != b["request_id"]
            assert b["parent"]["checkpoint_id"] == checkpoint["checkpoint_id"]
            assert b["proposal"]["selected_id"] == "cedar-32"
            assert b["pending"]
            assert (await s.get(a["request_id"]))["proposal_hash"] == a["proposal_hash"]
            with pytest.raises(Exception, match="No matching human approval"):
                await s.tools.call(
                    "create_purchase_order",
                    {
                        "request_id": b["request_id"],
                        "proposal_hash": b["proposal_hash"],
                    },
                )
            assert not s.store.orders()

    run(scenario())


def test_commit_boundary_rechecks_and_rejects_unauthorized(tmp_path):
    store = Store(tmp_path)
    req = PurchaseRequest().model_dump()
    p = {"request": req, "selected_id": "orbit-32", "total_inr": 810000}
    h = store.save_proposal("a", p)
    with pytest.raises(ValueError, match="human approval"):
        store.commit("a", h)
    store.authorize("a", h)
    with store.connect() as c:
        item = next(x for x in store.catalog() if x["id"] == "orbit-32")
        item["stock"] = 0
        c.execute(
            "UPDATE catalog SET payload=? WHERE id=?", (json.dumps(item), item["id"])
        )
    with pytest.raises(ValueError, match="Insufficient stock"):
        store.commit("a", h)
    assert not store.orders()


def test_unapproved_cheapest_supplier_is_never_selected(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            a = await s.create(PurchaseRequest())
            nova = next(x for x in a["policy"]["checks"] if x["id"] == "nova-32")
            assert not nova["eligible"]
            assert "Supplier is not approved" in nova["reasons"]
            assert a["recommendation"]["selected_id"] != "nova-32"

    run(scenario())


def test_api_validation_stale_decision_and_cross_origin(tmp_path):
    with TestClient(create_app(tmp_path, "demo")) as c:
        seed_client(c)
        assert c.get("/").status_code == 200
        assert c.get("/static/app.js").status_code == 200
        assert c.post("/api/requests", json={"quantity": 0}).status_code == 422
        assert (
            c.post(
                "/api/requests", json={}, headers={"origin": "https://evil.example"}
            ).status_code
            == 403
        )
        created = c.post("/api/requests", json={})
        assert created.status_code == 201
        a = created.json()
        assert c.get(f"/api/requests/{a['request_id']}").json()["pending"]
        login_client(c, "approver")
        assert (
            c.post(
                f"/api/requests/{a['request_id']}/decision",
                json={"action": "approve", "proposal_hash": "f" * 64},
            ).status_code
            == 409
        )
        assert c.get("/api/orders").json() == []
        assert c.get("/api/requests/unknown").status_code == 404


def test_model_failure_never_silently_falls_back(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:

            async def fail(ready):
                raise ConnectionError("Local model unavailable")

            s.agents.route = fail
            with pytest.raises(ConnectionError):
                await s.create(PurchaseRequest())
            rid = s.store.requests()[0]["id"]
            assert s.store.requests()[0]["status"] == "needs_attention"
            assert not s.store.orders()

            async def recover(ready):
                return ready[0]

            s.agents.route = recover
            out = await s.retry(rid)
            assert out["pending"]

    run(scenario())


def test_quote_terms_change_requires_new_approval(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            a = await s.create(PurchaseRequest())
            s.store.authorize(a["request_id"], a["proposal_hash"])
            with s.store.connect() as c:
                item = next(x for x in s.store.catalog() if x["id"] == "orbit-32")
                item["delivery_days"] = (
                    6  # Still within deadline, but differs from approved terms.
                )
                c.execute(
                    "UPDATE catalog SET payload=? WHERE id=?",
                    (json.dumps(item), item["id"]),
                )
            with pytest.raises(ValueError, match="quote terms changed"):
                s.store.commit(a["request_id"], a["proposal_hash"])
            assert not s.store.orders()

    run(scenario())


def test_model_reason_codes_are_grounded(tmp_path):
    from procureflow.agents import Agents
    from procureflow.schemas import Recommendation

    async def scenario():
        agents = Agents("demo")
        agents.mode = "ollama"
        candidates = [
            q for q in Store(tmp_path).catalog() if q["id"] in {"cedar-32", "orbit-32"}
        ]

        async def correct(schema, task, data):
            return Recommendation(
                selected_id="cedar-32",
                reason_codes=["longest_warranty", "largest_storage"],
            )

        agents.structured = correct
        out = await agents.recommend(PurchaseRequest().model_dump(), candidates)
        assert "INR 870,000" in out["rationale"]
        assert "12 days" in out["rationale"]
        assert any("7 days slower" in x for x in out["tradeoffs"])
        assert "$" not in out["rationale"]

        async def wrong(schema, task, data):
            return Recommendation(
                selected_id="cedar-32", reason_codes=["fastest_delivery"]
            )

        agents.structured = wrong
        with pytest.raises(ValueError, match="contradict"):
            await agents.recommend(PurchaseRequest().model_dump(), candidates)

    run(scenario())


def test_department_budget_cannot_be_overspent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = Store(tmp_path)
    item = next(x for x in store.catalog() if x["id"] == "atlas-16")
    # Two concurrent orders are individually eligible but jointly exceed allocation.
    item["stock"] = 100
    with store.connect() as c:
        c.execute(
            "UPDATE catalog SET payload=? WHERE id=?", (json.dumps(item), item["id"])
        )
    req = PurchaseRequest(quantity=40, budget_inr=3000000, min_ram_gb=16).model_dump()
    for rid in ["first", "second"]:
        p = {"request": req, "selected_id": "atlas-16", "total_inr": 2880000}
        h = store.save_proposal(rid, p)
        store.authorize(rid, h)

    def commit(rid):
        try:
            return store.commit(rid, h)
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, ["first", "second"]))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert len(store.orders()) == 1
    assert store.budget()["available_inr"] >= 0


def test_unicode_memory_is_bounded():
    turns = [{"role": "human", "text": "采购设备要求🙂" * 200} for _ in range(12)]
    memory = compact(turns)
    assert memory["context_bytes"] <= MAX_CONTEXT_BYTES
    assert memory["memory_summary"]


def test_background_job_and_downloadable_report(tmp_path):
    import time

    with TestClient(create_app(tmp_path, "demo")) as c:
        seed_client(c)
        assert c.get("/api/meta").json()["workspace_id"]
        r = c.post("/api/jobs", json={"simulate_timeout": True})
        assert r.status_code == 202
        rid = r.json()["request_id"]
        deadline = time.monotonic() + 10
        while True:
            job = c.get(f"/api/jobs/{rid}").json()
            if not job["running"]:
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert not job["error"]
        assert job["state"]["pending"]
        report = c.get(f"/api/requests/{rid}/report")
        assert report.status_code == 200
        assert report.headers["content-disposition"].startswith("attachment;")
        assert report.json()["proposal_hash"] == job["state"]["proposal_hash"]
        assert c.get("/api/orders").json() == []


def test_historical_brief_restores_the_selected_revision(tmp_path):
    async def scenario():
        async with open_service(tmp_path, "demo") as s:
            first = await s.create(PurchaseRequest())
            old_checkpoint = first["checkpoint_id"]
            revised = await s.decide(
                first["request_id"],
                Decision(
                    action="revise",
                    proposal_hash=first["proposal_hash"],
                    revision=PurchaseRequest(min_storage_gb=1024),
                ),
            )
            assert revised["request"]["min_storage_gb"] == 1024
            historical = await s.checkpoint(first["request_id"], old_checkpoint)
            assert historical["request"]["min_storage_gb"] == 512
            branch = await s.fork(
                first["request_id"],
                old_checkpoint,
                PurchaseRequest(**historical["request"]),
            )
            assert branch["request"]["min_storage_gb"] == 512
            assert branch["pending"]
            assert not s.store.orders()

    run(scenario())


def test_authentication_roles_and_ownership(tmp_path):
    with TestClient(create_app(tmp_path, "demo")) as c:
        assert c.get("/api/requests").status_code == 401
        seed_client(c)
        requester = login_client(c, "requester")
        a = c.post("/api/requests", json={}).json()
        assert a["owner_id"] == requester["id"]
        decision = {"action": "approve", "proposal_hash": a["proposal_hash"]}
        assert (
            c.post(
                f"/api/requests/{a['request_id']}/decision", json=decision
            ).status_code
            == 403
        )
        c.app.state.auth.create_user(
            "other-requester", "Test-password-12345", "requester"
        )
        login_client(c, "other-requester")
        assert c.get(f"/api/requests/{a['request_id']}").status_code == 403
        assert c.get("/api/requests").json() == []
        approver = login_client(c, "approver")
        assert c.post("/api/requests", json={}).status_code == 403
        revised = {
            "action": "revise",
            "proposal_hash": a["proposal_hash"],
            "revision": {},
        }
        assert (
            c.post(
                f"/api/requests/{a['request_id']}/decision", json=revised
            ).status_code
            == 403
        )
        out = c.post(f"/api/requests/{a['request_id']}/decision", json=decision)
        assert out.status_code == 200
        assert out.json()["order"]["approved_by"] == approver["id"]
        assert len(c.get("/api/orders").json()) == 1
        assert (
            "httponly"
            in c.post(
                "/api/auth/login",
                json={"username": "approver", "password": "Test-password-12345"},
            )
            .headers["set-cookie"]
            .lower()
        )
        assert c.post("/api/auth/logout").status_code == 200
        assert c.get("/api/requests").status_code == 401


def test_sessions_and_rate_limits_survive_restart(tmp_path):
    from procureflow.auth import Auth

    auth = Auth(tmp_path)
    user = auth.create_user("requester", "Unique-test-password-123", "requester")
    token, _ = auth.login("requester", "Unique-test-password-123")
    again = Auth(tmp_path)
    assert again.user(token)["id"] == user["id"]
    assert again.consume("test", 2)
    assert again.consume("test", 2)
    assert not Auth(tmp_path).consume("test", 2)
    again.logout(token)
    assert auth.user(token) is None
    with auth.connect() as c:
        row = c.execute("SELECT password_hash FROM users").fetchone()[0]
        session = c.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert "Unique-test-password" not in row
    assert session == 0


def test_login_bruteforce_limit(tmp_path):
    with TestClient(create_app(tmp_path, "demo")) as c:
        for _ in range(10):
            assert (
                c.post(
                    "/api/auth/login",
                    json={"username": "unknown", "password": "incorrect"},
                ).status_code
                == 401
            )
        assert (
            c.post(
                "/api/auth/login", json={"username": "unknown", "password": "incorrect"}
            ).status_code
            == 429
        )


def test_native_tool_loop_and_read_only_scope(tmp_path):
    from langchain_core.messages import AIMessage

    async def scenario():
        async with open_service(tmp_path, "demo") as service:

            class Model:
                def __init__(self, responses):
                    self.responses = iter(responses)

                def bind_tools(self, schemas):
                    assert {x["function"]["name"] for x in schemas} == {
                        "search_catalog",
                        "get_budget",
                    }
                    return self

                async def ainvoke(self, messages):
                    return next(self.responses)

            service.agents.mode = "ollama"
            service.agents.llm = Model(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_catalog",
                                "args": {"request_id": "model-cannot-change-this"},
                                "id": "one",
                                "type": "tool_call",
                            },
                            {
                                "name": "get_budget",
                                "args": {},
                                "id": "two",
                                "type": "tool_call",
                            },
                        ],
                    ),
                    AIMessage(content="Done"),
                ]
            )
            result = await service.agents.research(
                PurchaseRequest().model_dump(), service.tools, "authoritative-id"
            )
            assert len(result["trace"]) == 2
            assert (
                result["trace"][0]["executed_arguments"]["request_id"]
                == "authoritative-id"
            )
            service.agents.llm = Model(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "create_purchase_order",
                                "args": {},
                                "id": "bad",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            )
            with pytest.raises(PermissionError, match="read-only"):
                await service.agents.research(
                    PurchaseRequest().model_dump(), service.tools, "x"
                )
            assert not service.store.orders()

    run(scenario())


def test_mcp_actual_deadline_has_bounded_retries():
    from procureflow.tools import ProcurementTools, ToolFailure

    class SlowSession:
        async def call_tool(self, *args, **kwargs):
            await asyncio.sleep(1)

    async def scenario():
        tools = ProcurementTools(
            SlowSession(), {"search_catalog": {}}, timeout_seconds=0.01
        )
        with pytest.raises(ToolFailure, match="three attempts"):
            await tools.call("search_catalog")
        assert len(tools.events) == 3
        assert all(not e["ok"] for e in tools.events)

    run(scenario())


def test_semantic_summary_schema_and_recent_turns():
    from procureflow.agents import Agents
    from procureflow.memory import MemoryFacts

    async def scenario():
        agents = Agents("demo")
        agents.mode = "ollama"
        seen = []

        async def summarize(schema, task, data):
            assert schema is MemoryFacts
            seen.append(data)
            return MemoryFacts(
                preferences=["Prefer long warranty"],
                decisions=["Previous quote rejected"],
                unresolved_questions=["Confirm delivery deadline"],
            )

        agents.structured = summarize
        turns = [
            {"role": "request", "text": "Prefer long warranty"},
            {"role": "human revision", "text": "Reject previous quote"},
        ] + [{"role": "request", "text": "recent"}] * 4
        result = await agents.remember(turns, "")
        assert result["memory_facts"]["preferences"] == ["Prefer long warranty"]
        assert result["memory_facts"]["unresolved_questions"] == [
            "Confirm delivery deadline"
        ]
        assert len(result["recent_turns"]) == 4
        assert len(seen) == 2
        assert result["context_bytes"] <= 6000

    run(scenario())


def test_process_crash_after_order_commit_before_checkpoint(tmp_path):
    crash_code = """
import asyncio,os
from procureflow.service import open_service
from procureflow.schemas import PurchaseRequest,Decision
async def main():
 async with open_service(os.environ["PROCUREFLOW_HOME"],"demo") as s:
  state=await s.create(PurchaseRequest())
  with open(os.path.join(os.environ["PROCUREFLOW_HOME"],"request-id.txt"),"w") as f: f.write(state["request_id"])
  original=s.tools.call
  async def crash(name,args=None):
   result=await original(name,args)
   if name=="create_purchase_order": os._exit(77)
   return result
  s.tools.call=crash
  await s.decide(state["request_id"],Decision(action="approve",proposal_hash=state["proposal_hash"]))
asyncio.run(main())
"""
    env = dict(os.environ, PROCUREFLOW_HOME=str(tmp_path))
    process = subprocess.run(
        [sys.executable, "-c", crash_code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 77, process.stderr
    assert len(Store(tmp_path).orders()) == 1
    rid = (tmp_path / "request-id.txt").read_text()

    async def recover():
        async with open_service(tmp_path, "demo") as s:
            out = await s.retry(rid)
            assert out["status"] == "completed"
            assert len(s.store.orders()) == 1
            assert s.store.budget()["committed_inr"] == 810000

    run(recover())
