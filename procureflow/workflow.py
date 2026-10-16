import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .memory import compact
from .schemas import Decision, PurchaseRequest
from .store import now

MAX_REVISIONS = 4


class State(TypedDict, total=False):
    request_id: str
    request: dict
    mode: str
    status: str
    assessment: dict | None
    quotes: list[dict] | None
    policy: dict | None
    recommendation: dict | None
    proposal: dict | None
    proposal_hash: str
    order: dict | None
    revision: int
    route: str
    action: str
    audit: Annotated[list[dict], operator.add]
    recent_turns: list[dict]
    memory_summary: str
    context_bytes: int
    evicted_turns: int
    model_usage: list[dict]
    parent: dict | None


def event(actor, detail, **extra):
    return {"at": now(), "actor": actor, "detail": detail, **extra}


def build_graph(checkpointer, tools, agents, store):
    async def intake(s):
        req = PurchaseRequest.model_validate(s["request"]).model_dump()
        store.register(s["request_id"], req, agents.mode)
        return {
            "request": req,
            "status": "running",
            "audit": [event("Intake", "Purchase requirements validated")],
            "recent_turns": s.get("recent_turns", [])
            + [{"role": "request", "text": req["notes"] or req["title"]}],
        }

    async def supervisor(s):
        ready = []
        if not s.get("assessment"):
            ready.append("requirements")
        if s.get("quotes") is None:
            ready.append("suppliers")
        if not ready:
            ready = ["policy"] if s.get("policy") is None else ["recommendation"]
        worker = await agents.route(ready)
        return {
            "route": worker,
            "audit": [event("Supervisor", f"Delegated to {worker}")],
        }

    async def requirements(s):
        working_memory = {
            "summary": s.get("memory_summary", ""),
            "recent": [
                {
                    "role": t["role"],
                    "text": t["text"]
                    .encode("utf-8")[:250]
                    .decode("utf-8", errors="ignore"),
                }
                for t in s.get("recent_turns", [])[-4:]
            ],
        }
        assessment = await agents.assess(s["request"], working_memory)
        return {
            "assessment": assessment,
            "audit": [event("Requirements agent", assessment["summary"])],
        }

    async def suppliers(s):
        start = len(tools.events)
        # Scope: supplier worker sees only catalog discovery, never the write tool.
        result = await tools.call(
            "search_catalog",
            {
                "request_id": s["request_id"] + f":r{s.get('revision', 0)}",
                "simulate_timeout": s["request"]["simulate_timeout"],
            },
        )
        return {
            "quotes": result["quotes"],
            "audit": [
                event(
                    "Supplier worker",
                    "Retrieved quotes through MCP",
                    tools=tools.events[start:],
                )
            ],
        }

    async def policy(s):
        start = len(tools.events)
        result = await tools.call(
            "evaluate_quotes", {"request": s["request"], "quotes": s["quotes"]}
        )
        return {
            "policy": result,
            "audit": [
                event(
                    "Policy checker",
                    "Checked all quotes using deterministic rules",
                    tools=tools.events[start:],
                )
            ],
        }

    async def recommendation(s):
        eligible = {x["id"] for x in s["policy"]["checks"] if x["eligible"]}
        candidates = [x for x in s["quotes"] if x["id"] in eligible]
        if candidates:
            rec = await agents.recommend(s["request"], candidates)
            item = next(x for x in candidates if x["id"] == rec["selected_id"])
            proposal = {
                "request": s["request"],
                "selected_id": item["id"],
                "supplier": item["supplier"],
                "model": item["model"],
                "quantity": s["request"]["quantity"],
                "unit_inr": item["unit_inr"],
                "total_inr": item["unit_inr"] * s["request"]["quantity"],
                "delivery_days": item["delivery_days"],
                "warranty_years": item["warranty_years"],
                "ram_gb": item["ram_gb"],
                "storage_gb": item["storage_gb"],
                "revision": s.get("revision", 0),
            }
        else:
            rec = {
                "selected_id": "",
                "rationale": "No quote satisfies every hard constraint. Revise the requirements or reject this request.",
                "tradeoffs": [],
            }
            proposal = {
                "request": s["request"],
                "selected_id": "",
                "total_inr": 0,
                "revision": s.get("revision", 0),
            }
        h = store.save_proposal(s["request_id"], proposal)
        memory = compact(
            s.get("recent_turns", [])
            + [{"role": "recommendation", "text": rec["rationale"]}],
            s.get("memory_summary", ""),
        )
        store.status(s["request_id"], "awaiting_approval")
        return {
            "recommendation": rec,
            "proposal": proposal,
            "proposal_hash": h,
            "status": "awaiting_approval",
            "model_usage": s.get("model_usage", []) + list(agents.usage),
            **memory,
            "audit": [
                event("Recommendation agent", rec["rationale"]),
                event(
                    "Memory",
                    f"Active context: {memory['context_bytes']} bytes; summarized {memory['evicted_turns']} older turns",
                ),
            ],
        }

    async def approval(s):
        # No external side effects before interrupt: this node restarts on resume.
        payload = {
            "kind": "purchase_approval",
            "proposal_hash": s["proposal_hash"],
            "proposal": s["proposal"],
            "rationale": s["recommendation"]["rationale"],
            "can_approve": bool(s["proposal"]["selected_id"]),
            "can_revise": s.get("revision", 0) < MAX_REVISIONS,
        }
        d = Decision.model_validate(interrupt(payload))
        if d.proposal_hash != s["proposal_hash"]:
            raise ValueError("Stale approval")
        audit = [event("Human reviewer", d.action, note=d.note)]
        if d.action == "approve":
            if not s["proposal"]["selected_id"]:
                raise ValueError("Cannot approve an infeasible proposal")
            store.authorize(s["request_id"], d.proposal_hash)
            return {"action": "execute", "status": "approved", "audit": audit}
        store.invalidate(s["request_id"])
        if d.action == "reject":
            store.status(s["request_id"], "rejected")
            return {"action": "end", "status": "rejected", "audit": audit}
        if d.revision is None or s.get("revision", 0) >= MAX_REVISIONS:
            raise ValueError("Revision missing or revision limit exceeded")
        return {
            "action": "revise",
            "request": d.revision.model_dump(),
            "revision": s.get("revision", 0) + 1,
            "assessment": None,
            "quotes": None,
            "policy": None,
            "recommendation": None,
            "proposal": None,
            "proposal_hash": "",
            "order": None,
            "status": "running",
            "recent_turns": s.get("recent_turns", [])
            + [{"role": "human revision", "text": d.note or d.revision.notes}],
            "audit": audit,
        }

    async def execute(s):
        start = len(tools.events)
        order = await tools.call(
            "create_purchase_order",
            {"request_id": s["request_id"], "proposal_hash": s["proposal_hash"]},
        )
        store.status(s["request_id"], "completed")
        return {
            "order": order,
            "status": "completed",
            "audit": [
                event(
                    "Order executor",
                    "Approved purchase order created in local simulation",
                    tools=tools.events[start:],
                )
            ],
        }

    g = StateGraph(State)
    for name, fn in [
        ("intake", intake),
        ("supervisor", supervisor),
        ("requirements", requirements),
        ("suppliers", suppliers),
        ("policy", policy),
        ("recommendation", recommendation),
        ("approval", approval),
        ("execute", execute),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        lambda s: s["route"],
        {x: x for x in ["requirements", "suppliers", "policy", "recommendation"]},
    )
    for x in ["requirements", "suppliers", "policy"]:
        g.add_edge(x, "supervisor")
    g.add_edge("recommendation", "approval")
    g.add_conditional_edges(
        "approval",
        lambda s: s["action"],
        {"execute": "execute", "revise": "intake", "end": END},
    )
    g.add_edge("execute", END)
    return g.compile(checkpointer=checkpointer)
