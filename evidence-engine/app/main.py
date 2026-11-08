import logging
import secrets
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import files, health, jobs, merge, phone, upload
from app.api.websocket import router as ws_router
from app.config import settings
from app.services.neo4j_client import close_neo4j
from app.services.redis_client import close_redis

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(
        RedisSettings.from_dsn(settings.redis_url)
    )
    yield
    await app.state.arq_pool.close()
    await close_neo4j()
    await close_redis()


app = FastAPI(
    title="Ingestion Service",
    description="File ingestion pipeline for investigations console",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_service_key(request, call_next):
    if settings.service_api_key and request.url.path not in {
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
    }:
        supplied = request.headers.get("X-Evidence-Engine-Key", "")
        if not secrets.compare_digest(supplied, settings.service_api_key):
            return JSONResponse(status_code=401, content={"detail": "Invalid service credential"})
    return await call_next(request)

logger = logging.getLogger("app.refusals")


@app.exception_handler(StarletteHTTPException)
async def log_refusal(request, exc):
    """Say in the log why a write was refused. The access line alone ("400 Bad Request") hid that every refused
    upload of 28 Oct-8 Nov was a form part over 1 MiB ("Part exceeded maximum size of 1024KB.")."""
    if request.method != "GET" and 400 <= exc.status_code < 500 and exc.status_code != 404:
        logger.warning("request-refused %s %s %s: %s", request.method, request.url.path, exc.status_code,
                       str(exc.detail)[:500])
    return await http_exception_handler(request, exc)


app.include_router(health.router, tags=["health"])
app.include_router(upload.router, tags=["upload"])
app.include_router(files.router, tags=["files"])
# before jobs: POST /jobs/{id}/cancel must not fall into the generic /jobs/{id}/{action}
app.include_router(phone.router, tags=["phone"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(merge.router, tags=["merge"])
app.include_router(ws_router, tags=["websocket"])
