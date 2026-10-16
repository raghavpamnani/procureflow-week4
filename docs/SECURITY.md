# Accounts, roles, and approval authority

ProcureFlow is designed for a trusted local machine with separate application accounts. It is not a multi-tenant hosted purchasing service.

## Accounts and sessions

- No public signup and no shared seeded password. The local operator provisions accounts with `python -m procureflow.accounts`.
- Passwords use a unique 16-byte salt and scrypt (N=32768, r=8, p=3, 32-byte output). Verification uses constant-time comparison. Passwords are never sent to the model.
- Authentication issues a random opaque session token. Only its SHA-256 digest is stored. The HttpOnly, SameSite=Strict cookie expires after eight hours; logout revokes it server-side. Sessions survive process/container restart.
- Login attempts are limited to ten per peer per minute. Authenticated writes are limited to thirty per account per minute. Limits persist in SQLite. The background queue accepts at most four jobs.
- The provided scripts bind the application to localhost. Set `PROCUREFLOW_SECURE_COOKIE=1` behind correctly configured HTTPS. This is not a substitute for TLS, proxy hardening or tenant isolation.

## Role matrix

| Action | Requester | Independent approver |
|---|---|---|
| Create a request / checkpoint branch | Yes | No |
| Read requests | Own requests | All requests |
| Revise a brief | Its requester only | No |
| Approve / reject | No | Yes, only for another account's request |
| Retry research | Its requester only | No |
| Retry approved order execution | No | Yes, independently of requester |
| View orders | Own requests' orders | All orders |

Ownership comes from the authenticated session and is immutable. Supplying an owner or role in the request JSON does not grant authority. An exact proposal hash binds the decision to the reviewed action. The approver identity is saved in the audit and purchase-order receipt. The MCP commit tool independently checks the stored approver record before it writes. Model-visible tools remain read-only.

Legacy requests created before authentication cannot be newly approved through the authenticated interface without a verified requester; create a new brief instead.

## Trust boundary

HTTP and CLI operations require accounts. Python `open_service` is an internal trusted SDK used by tests and evaluation scripts; it can create isolated operator-owned fixtures without authentication. Someone who can execute arbitrary Python or edit the local SQLite files is already inside the operator trust boundary. Do not expose an arbitrary-code endpoint or give untrusted users filesystem access.

No payment service or real supplier API is connected. All orders are local simulations. Secure the host and backups if using real purchasing information. Current limitations include no MFA, password reset workflow, organization isolation, encrypted database, or tamper-proof external audit service.
