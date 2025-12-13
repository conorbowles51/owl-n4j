"""
Investigation Console - FastAPI Backend

Main entry point for the API server.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import API_HOST, API_PORT, CORS_ORIGINS
from routers import graph_router, chat_router, query_router, timeline_router
from services.neo4j_service import neo4j_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    print("Starting Investigation Console API...")
    yield
    # Shutdown
    print("Shutting down, closing Neo4j connection...")
    neo4j_service.close()


app = FastAPI(
    title="Investigation Console API",
    description="API for fraud investigation graph visualization and AI-powered queries",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graph_router)
app.include_router(chat_router)
app.include_router(query_router)
app.include_router(timeline_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Investigation Console API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    try:
        # Test Neo4j connection
        summary = neo4j_service.get_graph_summary()
        neo4j_status = "connected"
        node_count = summary.get("total_nodes", 0)
    except Exception as e:
        neo4j_status = f"error: {str(e)}"
        node_count = 0

    return {
        "status": "ok",
        "neo4j": neo4j_status,
        "nodes": node_count,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )
