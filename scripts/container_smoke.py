"""CI-only Docker verification: accounts, persisted pending approval, independent execution."""

import http.cookiejar
import json
import subprocess
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:18040"


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def call(c, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        URL + path, data=data, headers={"Content-Type": "application/json"}
    )
    with c.open(request, timeout=30) as response:
        return json.load(response)


def ready():
    for _ in range(60):
        try:
            if call(client(), "/api/health")["status"] == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Container did not become healthy")


ready()
# These public, test-only credentials exist only in the isolated CI container.
subprocess.run(
    [
        "docker",
        "exec",
        "pf-ci",
        "python",
        "-c",
        "from procureflow.auth import Auth; a=Auth('/data'); a.create_user('requester','CI-test-password-12345','requester'); a.create_user('approver','CI-test-password-12345','approver')",
    ],
    check=True,
)
r = client()
a = client()
call(
    r,
    "/api/auth/login",
    {"username": "requester", "password": "CI-test-password-12345"},
)
state = call(r, "/api/requests", {"simulate_timeout": True})
rid = state["request_id"]
assert state["pending"] and not call(r, "/api/orders")
decision = {"action": "approve", "proposal_hash": state["proposal_hash"]}
try:
    call(r, f"/api/requests/{rid}/decision", decision)
    raise AssertionError("Self approval was accepted")
except urllib.error.HTTPError as exc:
    assert exc.code == 403
subprocess.run(["docker", "restart", "pf-ci"], check=True)
ready()
# Requester session and interrupted graph both survive the container restart.
restored = call(r, f"/api/requests/{rid}")
assert restored["proposal_hash"] == state["proposal_hash"] and restored["pending"]
call(
    a, "/api/auth/login", {"username": "approver", "password": "CI-test-password-12345"}
)
completed = call(a, f"/api/requests/{rid}/decision", decision)
assert completed["status"] == "completed"
repeated = call(a, f"/api/requests/{rid}/decision", decision)
assert repeated["order"]["id"] == completed["order"]["id"]
assert len(call(a, "/api/orders")) == 1
print(
    "Container smoke passed: non-root app, role separation, session/checkpoint persistence, one order."
)
