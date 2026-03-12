"""
Vasaloppet Q&A Backend — application entry point.

Wires together the FastAPI app, CORS middleware, MCP client lifecycle,
and route handlers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import mcp_client
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the MCP client on startup, shut it down on exit."""
    await mcp_client.connect()
    yield
    await mcp_client.disconnect()


app = FastAPI(title="Vasaloppet Q&A Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The router carries /health, /api/defaults, /api/models, /api/ask
app.include_router(router)
