"""A real stdio MCP server. This process owns the catalog and order tools."""

import os

from mcp.server.fastmcp import FastMCP

from .schemas import PurchaseRequest
from .store import Store, check_item

mcp = FastMCP("ProcureFlow procurement tools")
store = Store(os.environ.get("PROCUREFLOW_HOME", ".runtime"))


@mcp.tool()
def search_catalog(request_id: str, simulate_timeout: bool = False) -> dict:
    """Retrieve supplier quotes. All sample prices are INR inclusive of GST."""
    if simulate_timeout and store.fail_once("catalog:" + request_id):
        return {"error": "Simulated transient supplier timeout", "retryable": True}
    return {
        "quotes": store.catalog(),
        "currency": "INR",
        "tax": "included",
        "source": "seeded local supplier catalog",
    }


@mcp.tool()
def get_budget() -> dict:
    """Read current Engineering budget commitments."""
    return store.budget()


@mcp.tool()
def evaluate_quotes(request: dict, quotes: list[dict]) -> dict:
    """Check supplier approval, specs, stock, warranty, delivery and budgets using code."""
    req = PurchaseRequest.model_validate(request).model_dump()
    # Never trust client-supplied prices or approval fields.
    fresh = {x["id"]: x for x in store.catalog()}
    available = store.budget()["available_inr"]
    results = []
    for quote in quotes:
        item = fresh.get(quote.get("id"))
        reasons = check_item(item, req, available)
        results.append(
            {"id": quote.get("id"), "eligible": not reasons, "reasons": reasons}
        )
    return {
        "checks": results,
        "budget": store.budget(),
        "policy": "Approved supplier; >=2-year warranty; all request constraints; department budget.",
    }


@mcp.tool()
def create_purchase_order(request_id: str, proposal_hash: str) -> dict:
    """Create a LOCAL SIMULATED order only for an independently stored human approval.

    Repeated execution of the same request/hash returns the existing order.
    """
    return store.commit(request_id, proposal_hash)


if __name__ == "__main__":
    mcp.run(transport="stdio")
