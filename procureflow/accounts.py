"""Local operator-only account provisioning. No public self-registration or seeded password."""

import argparse
import getpass
import os
import secrets
from pathlib import Path

from .auth import Auth


def main():
    parser = argparse.ArgumentParser(description="Provision local ProcureFlow accounts")
    parser.add_argument(
        "--home", default=os.environ.get("PROCUREFLOW_HOME", ".runtime")
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user")
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=["requester", "approver"], required=True)
    sub.add_parser("bootstrap-demo")
    args = parser.parse_args()
    auth = Auth(args.home)
    if args.command == "create-user":
        password = getpass.getpass("Password (12+ characters): ")
        if password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        user = auth.create_user(args.username, password, args.role)
        print("Created", user["username"], "with role", user["role"])
    else:
        with auth.connect() as c:
            if c.execute("SELECT count(*) FROM users").fetchone()[0]:
                raise SystemExit(
                    "Accounts already exist. Use create-user; no accounts were overwritten."
                )
        credentials = []
        for role in ["requester", "approver"]:
            password = secrets.token_urlsafe(18)
            auth.create_user(role, password, role)
            credentials.append(f"{role}: {password}")
        path = Path(args.home) / "demo-accounts.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(
                "LOCAL DEMO ACCOUNTS - keep private; never commit\n"
                + "\n".join(credentials)
                + "\n"
            )
        print("Created independent accounts. Private credentials saved to", path)


if __name__ == "__main__":
    main()
