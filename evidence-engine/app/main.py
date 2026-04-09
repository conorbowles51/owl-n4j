import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from app.api.routes import files, health, jobs, merge, upload
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

app.include_router(health.router, tags=["health"])
app.include_router(upload.router, tags=["upload"])
app.include_router(files.router, tags=["files"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(merge.router, tags=["merge"])
app.include_router(ws_router, tags=["websocket"])
