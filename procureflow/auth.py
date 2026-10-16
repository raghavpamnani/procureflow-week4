"""Local accounts, revocable persistent sessions, and persistent fixed-window limits."""

import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

COOKIE = "pf_session"
SESSION_SECONDS = 8 * 60 * 60


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    hashed = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=32768,
        r=8,
        p=3,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt$32768$8$3${salt.hex()}${hashed.hex()}"


def password_matches(password, encoded):
    try:
        _, n, r, p, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


class Auth:
    def __init__(self, home):
        self.db = Path(home) / "auth.sqlite"
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT CHECK(role IN ('requester','approver')), active INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS limits(bucket TEXT PRIMARY KEY, started REAL, hits INTEGER);
            """)
        # Matching a missing user still performs a password KDF.
        self.dummy = password_hash("dummy-not-a-real-account-password")

    def connect(self):
        c = sqlite3.connect(self.db, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def create_user(self, username, password, role):
        if role not in {"requester", "approver"}:
            raise ValueError("Role must be requester or approver")
        if not (3 <= len(username) <= 40) or not all(
            c.isalnum() or c in "-_" for c in username
        ):
            raise ValueError("Use a 3-40 character username: letters, numbers, - or _")
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must have 12-128 characters")
        uid = uuid.uuid4().hex
        with self.connect() as c:
            try:
                c.execute(
                    "INSERT INTO users(id,username,password_hash,role) VALUES (?,?,?,?)",
                    (uid, username, password_hash(password), role),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username already exists") from exc
        return {"id": uid, "username": username, "role": role}

    def login(self, username, password):
        with self.connect() as c:
            user = c.execute(
                "SELECT * FROM users WHERE username=?", (username,)
            ).fetchone()
            valid = password_matches(
                password, user["password_hash"] if user else self.dummy
            )
            if not user or not valid or not user["active"]:
                raise PermissionError("Invalid username or password")
            token = secrets.token_urlsafe(32)
            c.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            c.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    user["id"],
                    time.time() + SESSION_SECONDS,
                ),
            )
        return token, {k: user[k] for k in ["id", "username", "role"]}

    def user(self, token):
        if not token or len(token) > 256:
            return None
        with self.connect() as c:
            row = c.execute(
                "SELECT u.id,u.username,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        if token:
            with self.connect() as c:
                c.execute(
                    "DELETE FROM sessions WHERE token_hash=?",
                    (hashlib.sha256(token.encode()).hexdigest(),),
                )

    def consume(self, bucket, limit, window=60):
        now = time.time()
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM limits WHERE started<?", (now - 86400,))
            row = c.execute(
                "SELECT started,hits FROM limits WHERE bucket=?", (bucket,)
            ).fetchone()
            if not row or now - row["started"] >= window:
                c.execute(
                    "INSERT INTO limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET started=excluded.started,hits=1",
                    (bucket, now),
                )
                return True
            if row["hits"] >= limit:
                return False
            c.execute("UPDATE limits SET hits=hits+1 WHERE bucket=?", (bucket,))
            return True
