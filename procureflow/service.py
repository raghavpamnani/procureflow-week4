import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from .agents import Agents
from .store import Store
from .tools import connect_tools
from .workflow import MAX_REVISIONS, build_graph, event


class Conflict(ValueError):
    pass


class Service:
    def __init__(self, graph, tools, agents, store):
        self.graph, self.tools, self.agents, self.store = graph, tools, agents, store
        # Single local process: serialize writes, including human approvals.
        self.lock = asyncio.Lock()

    def config(self, rid, checkpoint_id=None):
        c = {"thread_id": rid}
        if checkpoint_id:
            c["checkpoint_id"] = checkpoint_id
        return {"configurable": c, "recursion_limit": 80}

    async def get(self, rid):
        state = await self.graph.aget_state(self.config(rid))
        if not state.values:
            raise KeyError("Request not found")
        pending = [i.value for task in state.tasks for i in task.interrupts]
        return {
            **state.values,
            "pending": pending,
            "next": list(state.next),
            "checkpoint_id": state.config["configurable"]["checkpoint_id"],
            "errors": [str(t.error) for t in state.tasks if t.error],
        }

    async def drive(self, rid, value, actor=None):
        self.agents.usage.clear()
        try:
            config = self.config(rid)
            config["configurable"]["decision_actor"] = actor
            await self.graph.ainvoke(value, config, durability="sync")
        except Exception:
            self.store.status(rid, "needs_attention")
            raise
        result = await self.get(rid)
        self.store.status(rid, result["status"])
        return result

    async def create(self, request, request_id=None, actor=None):
        async with self.lock:
            rid = request_id or uuid.uuid4().hex
            self.agents.usage.clear()
            if actor:
                self.store.bind_owner(rid, actor["id"])
            initial = {
                "request_id": rid,
                "request": request.model_dump(),
                "mode": self.agents.mode,
                "revision": 0,
                "owner_id": actor["id"] if actor else "trusted-local-sdk",
                "audit": [],
                "recent_turns": [],
                "memory_summary": "",
                "assessment": None,
                "quotes": None,
                "policy": None,
                "order": None,
            }
            return await self.drive(rid, initial)

    async def decide(self, rid, decision, actor=None):
        async with self.lock:
            state = await self.get(rid)
            owner = self.store.owner(rid)
            if actor and not owner and state["pending"]:
                raise PermissionError(
                    "This older request has no verified requester; create a new brief"
                )
            if owner:
                if not actor:
                    raise PermissionError("Authenticated reviewer required")
                if decision.action in {"approve", "reject"} and (
                    actor["role"] != "approver" or actor["id"] == owner
                ):
                    raise PermissionError(
                        "Only an independent approver can approve or reject"
                    )
                if decision.action == "revise" and actor["id"] != owner:
                    raise PermissionError("Only the requester can revise this brief")
            if not state["pending"]:
                if (
                    decision.action == "approve"
                    and (state.get("order") or {}).get("proposal_hash")
                    == decision.proposal_hash
                ):
                    return state
                raise Conflict("This request is not waiting for a decision")
            if decision.proposal_hash != state["proposal_hash"]:
                raise Conflict(
                    "Proposal changed. Review the latest version before deciding."
                )
            if decision.action == "revise" and state["mode"] != self.agents.mode:
                raise Conflict(
                    "Restart in the original model mode before revising this request"
                )
            if decision.action == "approve" and not state["proposal"]["selected_id"]:
                raise Conflict("No eligible quote; revise or reject")
            if decision.action == "revise" and (
                not decision.revision or state.get("revision", 0) >= MAX_REVISIONS
            ):
                raise Conflict(
                    "Provide revised requirements; at most four revisions are allowed"
                )
            return await self.drive(
                rid, Command(resume=decision.model_dump()), actor=actor
            )

    async def retry(self, rid):
        async with self.lock:
            s = await self.get(rid)
            if s["pending"] or not s["next"]:
                raise Conflict("Only a failed or interrupted execution can be retried")
            if s["mode"] != self.agents.mode:
                raise Conflict("Restart in the same model mode before retrying")
            return await self.drive(rid, None)

    async def history(self, rid):
        await self.get(rid)
        return [
            {
                "checkpoint_id": s.config["configurable"]["checkpoint_id"],
                "at": s.created_at,
                "next": list(s.next),
                "status": s.values.get("status", "starting"),
                "revision": s.values.get("revision", 0),
                "has_request": bool(s.values.get("request")),
            }
            async for s in self.graph.aget_state_history(self.config(rid))
        ]

    async def checkpoint(self, rid, checkpoint_id):
        await self.get(rid)
        snapshot = await self.graph.aget_state(self.config(rid, checkpoint_id))
        if not snapshot.values.get("request"):
            raise KeyError("Checkpoint not found or does not contain a purchase brief")
        return {
            "request": snapshot.values["request"],
            "revision": snapshot.values.get("revision", 0),
            "checkpoint_id": checkpoint_id,
        }

    async def fork(self, rid, checkpoint_id, request, actor=None):
        async with self.lock:
            await self.get(rid)
            source = await self.graph.aget_state(self.config(rid, checkpoint_id))
            if not source.values.get("request"):
                raise Conflict("Choose a checkpoint after intake")
            new_id = uuid.uuid4().hex
            values = dict(source.values)
            # Branch to a NEW request, explicitly clear outputs and all approvals.
            values.update(
                request_id=new_id,
                request=request.model_dump(),
                mode=self.agents.mode,
                status="running",
                revision=0,
                assessment=None,
                quotes=None,
                policy=None,
                recommendation=None,
                proposal=None,
                proposal_hash="",
                order=None,
                action="",
                parent={"request_id": rid, "checkpoint_id": checkpoint_id},
                audit=[
                    event(
                        "Checkpoint branch",
                        "New alternative requires independent approval",
                        source=rid,
                    )
                ],
                recent_turns=source.values.get("recent_turns", []),
                memory_summary=source.values.get("memory_summary", ""),
                model_usage=[],
            )
            if actor:
                self.store.bind_owner(new_id, actor["id"])
                values["owner_id"] = actor["id"]
            values["decision_actor"] = None
            self.store.register(new_id, values["request"], self.agents.mode)
            await self.graph.aupdate_state(
                self.config(new_id), values, as_node="intake"
            )
            self.agents.usage.clear()
            return await self.drive(new_id, None)


@asynccontextmanager
async def open_service(home=None, mode=None):
    home = Path(home or os.environ.get("PROCUREFLOW_HOME", ".runtime")).resolve()
    mode = mode or os.environ.get("PROCUREFLOW_MODE", "demo")
    if mode not in {"demo", "ollama"}:
        raise ValueError("PROCUREFLOW_MODE must be demo or ollama")
    store = Store(home)
    agents = Agents(
        mode,
        os.environ.get("PROCUREFLOW_MODEL", "qwen3:1.7b"),
        os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    async with connect_tools(home) as tools:
        async with AsyncSqliteSaver.from_conn_string(
            str(home / "checkpoints.sqlite")
        ) as saver:
            await saver.setup()
            graph = build_graph(saver, tools, agents, store)
            yield Service(graph, tools, agents, store)
