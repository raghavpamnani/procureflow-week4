import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .schemas import Decision, ForkRequest, PurchaseRequest
from .service import Conflict, open_service
from .store import digest

STATIC = Path(__file__).with_name("static")


def create_app(home=None, mode=None):
    @asynccontextmanager
    async def lifespan(app):
        async with open_service(home, mode) as service:
            app.state.service = service
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
        # Local single-user application. Block browser cross-origin mutations.
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return JSONResponse(
                {"detail": "Cross-origin writes are disabled"}, status_code=403
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
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
        rid = uuid.uuid4().hex
        service = request.app.state.service
        service.store.register(rid, body.model_dump(), service.agents.mode, "queued")

        async def work():
            try:
                await service.create(body, request_id=rid)
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
        return request.app.state.service.store.requests()

    @app.post("/api/requests", status_code=201)
    async def create(body: PurchaseRequest, request: Request):
        return await request.app.state.service.create(body)

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
        return await request.app.state.service.decide(rid, body)

    @app.post("/api/requests/{rid}/retry")
    async def retry(rid: str, request: Request):
        return await request.app.state.service.retry(rid)

    @app.get("/api/requests/{rid}/history")
    async def history(rid: str, request: Request):
        return await request.app.state.service.history(rid)

    @app.get("/api/requests/{rid}/checkpoints/{checkpoint_id}")
    async def checkpoint(rid: str, checkpoint_id: str, request: Request):
        return await request.app.state.service.checkpoint(rid, checkpoint_id)

    @app.post("/api/requests/{rid}/fork", status_code=201)
    async def fork(rid: str, body: ForkRequest, request: Request):
        return await request.app.state.service.fork(
            rid, body.checkpoint_id, body.request
        )

    @app.get("/api/orders")
    async def orders(request: Request):
        return request.app.state.service.store.orders()

    return app


app = create_app()
