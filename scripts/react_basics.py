"""Day 16: raw Ollama SDK tool loop, deliberately without LangGraph/LangChain.

Run from the project root: python scripts/react_basics.py
Read-only catalog access. No approval or purchasing capability is exposed.
"""

import json
import os

from ollama import Client

from procureflow.schemas import PurchaseRequest
from procureflow.store import Store, check_item

client = Client(
    host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"), timeout=90
)
store = Store(os.environ.get("PROCUREFLOW_HOME", ".runtime"))


def lookup_laptops(
    min_ram_gb: int = 32, quantity: int = 10, budget_inr: int = 900000
) -> str:
    """Find eligible laptop quotes, with quantity-adjusted tax-inclusive INR totals."""
    req = PurchaseRequest(
        min_ram_gb=min_ram_gb, quantity=quantity, budget_inr=budget_inr
    ).model_dump()
    return json.dumps(
        [
            {**q, "total_inr": q["unit_inr"] * quantity}
            for q in store.catalog()
            if not check_item(q, req, store.budget()["available_inr"])
        ]
    )


messages = [
    {
        "role": "system",
        "content": "Use the read-only lookup_laptops tool to compare laptops. Give a concise factual recommendation. Do not invent quotes or claim a purchase. /no_think",
    },
    {
        "role": "user",
        "content": "Compare 32 GB laptops for ten developers, budget INR 900000. Only approved suppliers.",
    },
]
for step in range(6):
    response = client.chat(
        model=os.environ.get("PROCUREFLOW_MODEL", "qwen3:1.7b"),
        messages=messages,
        tools=[lookup_laptops],
        think=False,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 700},
    )
    messages.append(response.message.model_dump(exclude_none=True))
    if not response.message.tool_calls:
        print("Unvalidated model answer (read-only learning example):")
        print(response.message.content)
        break
    if len(response.message.tool_calls) > 2:
        raise RuntimeError("Exceeded the two-tool-calls-per-step limit")
    for call in response.message.tool_calls:
        if call.function.name != "lookup_laptops":
            observation = "Tool is not permitted"
        else:
            try:
                observation = lookup_laptops(
                    int(call.function.arguments.get("min_ram_gb", 32)),
                    int(call.function.arguments.get("quantity", 10)),
                    int(call.function.arguments.get("budget_inr", 900000)),
                )
            except (TypeError, ValueError) as exc:
                observation = f"Invalid arguments: {exc}"
        print(
            f"Step {step + 1}: {call.function.name} -> {len(observation)} characters observed"
        )
        messages.append(
            {"role": "tool", "tool_name": call.function.name, "content": observation}
        )
else:
    raise RuntimeError("Stopped at the six-iteration safety limit")
