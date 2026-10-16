import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path

from .auth import Auth
from .schemas import Decision, PurchaseRequest
from .service import open_service


async def run(args):
    home = Path(args.home or os.environ.get("PROCUREFLOW_HOME", ".runtime")).resolve()
    auth = Auth(home)
    if not auth.consume("cli-login:" + args.username, 10):
        raise PermissionError("Too many CLI login attempts")
    token, actor = auth.login(args.username, getpass.getpass("Account password: "))
    auth.logout(token)  # CLI identity is used for this operation only.
    async with open_service(home, args.mode) as s:
        if args.command == "new" and actor["role"] != "requester":
            raise PermissionError("Only requesters can create requests")
        if (
            hasattr(args, "id")
            and actor["role"] != "approver"
            and s.store.owner(args.id) != actor["id"]
        ):
            raise PermissionError("This request belongs to another user")
        if args.command == "new":
            req = PurchaseRequest(
                quantity=args.quantity,
                budget_inr=args.budget,
                min_ram_gb=args.ram,
                delivery_days=args.days,
                priority=args.priority,
                simulate_timeout=args.timeout,
            )
            out = await s.create(req, actor=actor)
        elif args.command == "show":
            out = await s.get(args.id)
        elif args.command == "history":
            out = await s.history(args.id)
        elif args.command in {"approve", "reject"}:
            current = await s.get(args.id)
            if args.command == "approve":
                print(json.dumps(current["proposal"], indent=2))
                if (
                    input("Type APPROVE to create this simulated purchase order: ")
                    != "APPROVE"
                ):
                    return
            out = await s.decide(
                args.id,
                Decision(action=args.command, proposal_hash=current["proposal_hash"]),
                actor=actor,
            )
        else:
            out = [
                r
                for r in s.store.requests()
                if actor["role"] == "approver" or s.store.owner(r["id"]) == actor["id"]
            ]
        print(json.dumps(out, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="ProcureFlow durable purchasing workflows"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--home", default=None)
    parser.add_argument("--mode", choices=["demo", "ollama"], default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("new")
    p.add_argument("--quantity", type=int, default=10)
    p.add_argument("--budget", type=int, default=900000)
    p.add_argument("--ram", type=int, choices=[16, 32, 64], default=32)
    p.add_argument("--days", type=int, default=14)
    p.add_argument(
        "--priority", choices=["value", "performance", "delivery"], default="value"
    )
    p.add_argument("--timeout", action="store_true")
    for name in ["show", "history", "approve", "reject"]:
        commands.add_parser(name).add_argument("id")
    commands.add_parser("list")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
