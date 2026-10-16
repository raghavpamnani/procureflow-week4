"""Business data and the independent commit boundary. Amounts are integer INR, tax inclusive."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Store:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = self.home / "business.sqlite"
        with self.connect() as c:
            c.executescript("""
              CREATE TABLE IF NOT EXISTS catalog(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, title TEXT, status TEXT, mode TEXT, updated TEXT);
              CREATE TABLE IF NOT EXISTS proposals(request_id TEXT PRIMARY KEY, hash TEXT, payload TEXT, approved INTEGER DEFAULT 0);
              CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, request_id TEXT UNIQUE, proposal_hash TEXT, payload TEXT, created TEXT);
              CREATE TABLE IF NOT EXISTS faults(key TEXT PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS ownership(request_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS approval_actors(request_id TEXT PRIMARY KEY, proposal_hash TEXT, user_id TEXT, role TEXT);
            """)
            if not c.execute("SELECT count(*) FROM catalog").fetchone()[0]:
                for item in json.loads((ROOT / "data/catalog.json").read_text()):
                    c.execute(
                        "INSERT INTO catalog VALUES (?,?)",
                        (item["id"], json.dumps(item)),
                    )

    def connect(self):
        c = sqlite3.connect(self.db, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def catalog(self):
        with self.connect() as c:
            return [
                json.loads(x[0])
                for x in c.execute("SELECT payload FROM catalog ORDER BY id")
            ]

    def budget(self):
        with self.connect() as c:
            spent = sum(
                json.loads(x[0])["total_inr"]
                for x in c.execute("SELECT payload FROM orders")
            )
        return {
            "department": "Engineering",
            "allocation_inr": 5000000,
            "committed_inr": spent,
            "available_inr": 5000000 - spent,
        }

    def fail_once(self, key):
        with self.connect() as c:
            return (
                c.execute("INSERT OR IGNORE INTO faults VALUES (?)", (key,)).rowcount
                == 1
            )

    def register(self, rid, request, mode, status="running"):
        with self.connect() as c:
            c.execute(
                "INSERT INTO requests VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,status=excluded.status,updated=excluded.updated",
                (rid, request["title"], status, mode, now()),
            )

    def bind_owner(self, rid, user_id):
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO ownership VALUES (?,?)", (rid, user_id))
            if (
                c.execute(
                    "SELECT user_id FROM ownership WHERE request_id=?", (rid,)
                ).fetchone()[0]
                != user_id
            ):
                raise PermissionError("Request ownership cannot be reassigned")

    def owner(self, rid):
        with self.connect() as c:
            row = c.execute(
                "SELECT user_id FROM ownership WHERE request_id=?", (rid,)
            ).fetchone()
            return row[0] if row else None

    def status(self, rid, status):
        with self.connect() as c:
            c.execute(
                "UPDATE requests SET status=?,updated=? WHERE id=?",
                (status, now(), rid),
            )

    def requests(self):
        with self.connect() as c:
            return [
                dict(x)
                for x in c.execute("SELECT * FROM requests ORDER BY updated DESC")
            ]

    def save_proposal(self, rid, proposal):
        h = digest(proposal)
        with self.connect() as c:
            c.execute(
                "INSERT INTO proposals VALUES (?,?,?,0) ON CONFLICT(request_id) DO UPDATE SET hash=excluded.hash,payload=excluded.payload,approved=0",
                (rid, h, json.dumps(proposal)),
            )
        return h

    def authorize(self, rid, h, reviewer=None):
        owner = self.owner(rid)
        if owner and (
            not reviewer
            or reviewer.get("role") != "approver"
            or reviewer.get("id") == owner
        ):
            raise PermissionError(
                "A different authenticated approver must approve this request"
            )
        with self.connect() as c:
            if reviewer:
                c.execute(
                    "INSERT INTO approval_actors VALUES (?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET proposal_hash=excluded.proposal_hash,user_id=excluded.user_id,role=excluded.role",
                    (rid, h, reviewer["id"], reviewer["role"]),
                )
            if (
                c.execute(
                    "UPDATE proposals SET approved=1 WHERE request_id=? AND hash=?",
                    (rid, h),
                ).rowcount
                != 1
            ):
                raise ValueError("Proposal changed; review the latest version.")

    def invalidate(self, rid):
        with self.connect() as c:
            c.execute("UPDATE proposals SET approved=0 WHERE request_id=?", (rid,))

    def commit(self, rid, h):
        # Approval, fresh policy checks, stock, budget, and order insertion share one transaction.
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT payload,proposal_hash FROM orders WHERE request_id=?", (rid,)
            ).fetchone()
            if existing:
                if existing[1] != h:
                    raise ValueError(
                        "This request already has an order for another proposal."
                    )
                return json.loads(existing[0])
            row = c.execute(
                "SELECT payload,hash,approved FROM proposals WHERE request_id=?", (rid,)
            ).fetchone()
            if not row or row[1] != h or row[2] != 1:
                raise ValueError("No matching human approval. Order creation blocked.")
            owner = c.execute(
                "SELECT user_id FROM ownership WHERE request_id=?", (rid,)
            ).fetchone()
            actor = c.execute(
                "SELECT proposal_hash,user_id,role FROM approval_actors WHERE request_id=?",
                (rid,),
            ).fetchone()
            if owner and (
                not actor
                or actor[0] != h
                or actor[1] == owner[0]
                or actor[2] != "approver"
            ):
                raise PermissionError("Missing independent approver identity")
            p = json.loads(row[0])
            req = p["request"]
            row = c.execute(
                "SELECT payload FROM catalog WHERE id=?", (p["selected_id"],)
            ).fetchone()
            item = json.loads(row[0]) if row else None
            spent = sum(
                json.loads(x[0])["total_inr"]
                for x in c.execute("SELECT payload FROM orders")
            )
            violations = check_item(item, req, 5000000 - spent)
            if violations or item["unit_inr"] * req["quantity"] != p["total_inr"]:
                raise ValueError(
                    "Fresh policy check failed: "
                    + "; ".join(violations or ["quote changed"])
                )
            for field in [
                "supplier",
                "model",
                "unit_inr",
                "delivery_days",
                "warranty_years",
                "ram_gb",
                "storage_gb",
            ]:
                if field in p and p[field] != item[field]:
                    raise ValueError(
                        "Approved quote terms changed; obtain a new approval"
                    )
            order = {
                "id": "PO-" + rid[:8].upper(),
                "request_id": rid,
                "supplier": item["supplier"],
                "model": item["model"],
                "quantity": req["quantity"],
                "unit_inr": item["unit_inr"],
                "total_inr": p["total_inr"],
                "proposal_hash": h,
                "created": now(),
                "environment": "local simulation",
                "approved_by": actor[1] if actor else "trusted-local-sdk",
            }
            item["stock"] -= req["quantity"]
            c.execute(
                "UPDATE catalog SET payload=? WHERE id=?",
                (json.dumps(item), item["id"]),
            )
            c.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?)",
                (order["id"], rid, h, json.dumps(order), now()),
            )
            c.execute("UPDATE proposals SET approved=0 WHERE request_id=?", (rid,))
            return order

    def orders(self):
        with self.connect() as c:
            return [
                json.loads(x[0])
                for x in c.execute("SELECT payload FROM orders ORDER BY created DESC")
            ]


def check_item(item, req, available):
    if not item:
        return ["Unknown product"]
    checks = [
        (item["approved"], "Supplier is not approved"),
        (item["ram_gb"] >= req["min_ram_gb"], "RAM below requirement"),
        (item["storage_gb"] >= req["min_storage_gb"], "Storage below requirement"),
        (item["stock"] >= req["quantity"], "Insufficient stock"),
        (item["delivery_days"] <= req["delivery_days"], "Delivery misses deadline"),
        (
            item["unit_inr"] * req["quantity"] <= req["budget_inr"],
            "Exceeds request budget",
        ),
        (
            item["unit_inr"] * req["quantity"] <= available,
            "Exceeds remaining department budget",
        ),
        (item["warranty_years"] >= 2, "Warranty below two-year policy"),
    ]
    return [reason for passed, reason in checks if not passed]
