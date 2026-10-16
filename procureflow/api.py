import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import COOKIE, SESSION_SECONDS, Auth
from .schemas import Decision, ForkRequest, PurchaseRequest
from .service import Conflict, open_service
from .store import digest

STATIC = Path(__file__).with_name("static")


def create_app(home=None, mode=None):
    @asynccontextmanager
    async def lifespan(app):
        async with open_service(home, mode) as service:
            app.state.service = service
            app.state.auth = Auth(service.store.home)
            app.state.tasks = {}
            app.state.job_errors = {}
            yield
            tasks = list(app.state.tasks.values())
            # Finish checkpoint writes before closing MCP and SQLite resources.
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="ProcureFlow", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        # Local multi-account application. Block browser cross-origin mutations.
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse(
                {"detail": "Cross-origin writes are disabled"}, status_code=403
            )
        if request.url.path.startswith("/api/") and request.url.path not in {
            "/api/auth/login",
            "/api/auth/session",
            "/api/health",
        }:
            actor = request.app.state.auth.user(request.cookies.get(COOKIE))
            if not actor:
                return JSONResponse({"detail": "Sign in to continue"}, status_code=401)
            request.state.actor = actor
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if not request.app.state.auth.consume("write:" + actor["id"], 30):
                    return JSONResponse(
                        {"detail": "Write rate limit exceeded; retry in a minute"},
                        status_code=429,
                    )
            parts = request.url.path.strip("/").split("/")
            if len(parts) >= 3 and parts[1] in {"requests", "jobs"}:
                rid = parts[2]
                store = request.app.state.service.store
                if (
                    any(x["id"] == rid for x in store.requests())
                    and actor["role"] != "approver"
                    and store.owner(rid) != actor["id"]
                ):
                    return JSONResponse(
                        {"detail": "This request belongs to another user"},
                        status_code=403,
                    )
            creating = request.method == "POST" and (
                request.url.path in {"/api/jobs", "/api/requests"}
                or request.url.path.endswith("/fork")
            )
            if creating and actor["role"] != "requester":
                return JSONResponse(
                    {"detail": "Only requesters can create purchase requests"},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    class Login(BaseModel):
        username: str = Field(min_length=3, max_length=40)
        password: str = Field(min_length=1, max_length=128)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "procureflow"}

    @app.get("/api/auth/session")
    async def session(request: Request):
        auth = request.app.state.auth
        with auth.connect() as c:
            configured = bool(c.execute("SELECT count(*) FROM users").fetchone()[0])
        return {
            "user": auth.user(request.cookies.get(COOKIE)),
            "configured": configured,
        }

    @app.post("/api/auth/login")
    async def login(body: Login, request: Request):
        auth = request.app.state.auth
        peer = request.client.host if request.client else "local"
        if not auth.consume("login:" + peer, 10):
            raise HTTPException(429, "Too many login attempts; retry in a minute")
        try:
            token, user = await run_in_threadpool(
                auth.login, body.username, body.password
            )
        except PermissionError:
            raise HTTPException(401, "Invalid username or password") from None
        response = JSONResponse({"user": user})
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            samesite="strict",
            secure=os.environ.get("PROCUREFLOW_SECURE_COOKIE") == "1",
        )
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        request.app.state.auth.logout(request.cookies.get(COOKIE))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/meta")
    async def meta(request: Request):
        s = request.app.state.service
        return {
            "workspace_id": digest(str(s.store.home))[:12],
            "mode": s.agents.mode,
            "model": s.agents.model if s.agents.mode == "ollama" else None,
            "tools": s.tools.schemas,
            "budget": s.store.budget(),
            "environment": "Local simulation · no external purchases",
        }

    @app.post("/api/jobs", status_code=202)
    async def start_job(body: PurchaseRequest, request: Request):
        if len(request.app.state.tasks) >= 4:
            raise HTTPException(
                429, "Four requests are already queued; wait for one to finish"
            )
        rid = uuid.uuid4().hex
        service = request.app.state.service
        service.store.register(rid, body.model_dump(), service.agents.mode, "queued")
        actor = request.state.actor
        service.store.bind_owner(rid, actor["id"])

        async def work():
            try:
                await service.create(body, request_id=rid, actor=actor)
            except Exception as exc:
                request.app.state.job_errors[rid] = str(exc)

        task = asyncio.create_task(work())
        request.app.state.tasks[rid] = task
        task.add_done_callback(lambda _: request.app.state.tasks.pop(rid, None))
        return {"request_id": rid}

    @app.get("/api/jobs/{rid}")
    async def job_status(rid: str, request: Request):
        service = request.app.state.service
        try:
            state = await service.get(rid)
        except KeyError:
            if not any(r["id"] == rid for r in service.store.requests()):
                raise
            state = {"request_id": rid, "status": "queued", "audit": []}
        running = rid in request.app.state.tasks
        error = request.app.state.job_errors.get(rid)
        return {"running": running, "error": error, "state": state}

    @app.get("/api/requests")
    async def requests(request: Request):
        store = request.app.state.service.store
        actor = request.state.actor
        return [
            r
            for r in store.requests()
            if actor["role"] == "approver" or store.owner(r["id"]) == actor["id"]
        ]

    @app.post("/api/requests", status_code=201)
    async def create(body: PurchaseRequest, request: Request):
        return await request.app.state.service.create(body, actor=request.state.actor)

    @app.get("/api/requests/{rid}")
    async def get(rid: str, request: Request):
        return await request.app.state.service.get(rid)

    @app.get("/api/requests/{rid}/report")
    async def report(rid: str, request: Request):
        state = await request.app.state.service.get(rid)
        return JSONResponse(
            state,
            headers={
                "Content-Disposition": f'attachment; filename="procureflow-{state["request_id"][:8]}.json"'
            },
        )

    @app.post("/api/requests/{rid}/decision")
    async def decide(rid: str, body: Decision, request: Request):
        return await request.app.state.service.decide(
            rid, body, actor=request.state.actor
        )

    @app.post("/api/requests/{rid}/retry")
    async def retry(rid: str, request: Request):
        s = request.app.state.service
        state = await s.get(rid)
        actor = request.state.actor
        if "execute" in state["next"]:
            if actor["role"] != "approver" or s.store.owner(rid) == actor["id"]:
                raise PermissionError(
                    "Only an independent approver can retry order execution"
                )
        elif s.store.owner(rid) != actor["id"]:
            raise PermissionError("Only the requester can retry research")
        return await s.retry(rid)

    @app.get("/api/requests/{rid}/history")
    async def history(rid: str, request: Request):
        return await request.app.state.service.history(rid)

    @app.get("/api/requests/{rid}/checkpoints/{checkpoint_id}")
    async def checkpoint(rid: str, checkpoint_id: str, request: Request):
        return await request.app.state.service.checkpoint(rid, checkpoint_id)

    @app.post("/api/requests/{rid}/fork", status_code=201)
    async def fork(rid: str, body: ForkRequest, request: Request):
        return await request.app.state.service.fork(
            rid, body.checkpoint_id, body.request, actor=request.state.actor
        )

    @app.get("/api/orders")
    async def orders(request: Request):
        store = request.app.state.service.store
        actor = request.state.actor
        return [
            o
            for o in store.orders()
            if actor["role"] == "approver"
            or store.owner(o["request_id"]) == actor["id"]
        ]

    return app


app = create_app()
