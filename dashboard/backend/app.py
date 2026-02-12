"""
OpenFang Dashboard — FastAPI Backend

Provides REST API and WebSocket endpoints for the
management dashboard. Serves the frontend static files.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from openfang.registry import AutomationRegistry, ComponentRegistry

from dashboard.backend.routes import automations, components, costs, insights, logs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize registries on startup."""
    registry = AutomationRegistry()
    await registry.initialize()
    app.state.automation_registry = registry

    component_registry = ComponentRegistry()
    component_registry.discover()
    app.state.component_registry = component_registry

    yield


app = FastAPI(
    title="OpenFang Dashboard",
    description="Management dashboard for OpenFang automations",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(automations.router, prefix="/api/automations", tags=["automations"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(components.router, prefix="/api/components", tags=["components"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(costs.router, prefix="/api/costs", tags=["costs"])


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "openfang-dashboard"}
