"""Deterministic golden scenarios. Real graph, MCP and policies; no LLM claims."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone

from procureflow.schemas import PurchaseRequest
from procureflow.service import open_service

CASES = [
    ("value", {}, "orbit-32"),
    ("performance", {"priority": "performance"}, "cedar-32"),
    ("delivery", {"priority": "delivery"}, "orbit-32"),
    ("infeasible budget", {"budget_inr": 700000}, ""),
    ("infeasible RAM", {"min_ram_gb": 64}, ""),
    ("infeasible deadline", {"delivery_days": 4}, ""),
    ("16 GB request", {"min_ram_gb": 16}, "atlas-16"),
    ("1 TB requirement", {"min_storage_gb": 1024}, "cedar-32"),
]


async def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix="procureflow-eval-") as home:
        async with open_service(home, "demo") as s:
            for name, fields, expected in CASES:
                a = await s.create(PurchaseRequest(**fields))
                actual = a["proposal"]["selected_id"]
                passed = (
                    actual == expected and bool(a["pending"]) and not s.store.orders()
                )
                rows.append(
                    {
                        "scenario": name,
                        "expected": expected,
                        "actual": actual,
                        "passed": passed,
                    }
                )
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "mode": "demo - deterministic golden scenarios, not an LLM benchmark",
        "passed": sum(x["passed"] for x in rows),
        "total": len(rows),
        "scenarios": rows,
    }
    print(json.dumps(report, indent=2))
    if not all(x["passed"] for x in rows):
        raise SystemExit(1)


asyncio.run(main())
