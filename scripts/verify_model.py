"""Real local-model smoke test. Never approves or creates an order."""

import asyncio
import json
import tempfile
import time

from procureflow.schemas import PurchaseRequest
from procureflow.service import open_service


async def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="procureflow-model-") as home:
        async with open_service(home, "ollama") as service:
            s = await service.create(PurchaseRequest(simulate_timeout=True))
            assert s["pending"], "Human approval interrupt not reached"
            assert s["proposal"]["selected_id"] in {"orbit-32", "cedar-32"}
            assert not service.store.orders()
            print(
                json.dumps(
                    {
                        "model": service.agents.model,
                        "seconds": round(time.monotonic() - started, 2),
                        "status": s["status"],
                        "selected_id": s["proposal"]["selected_id"],
                        "rationale": s["recommendation"]["rationale"],
                        "model_calls": s["model_usage"],
                        "order_count": 0,
                    },
                    indent=2,
                )
            )


asyncio.run(main())
