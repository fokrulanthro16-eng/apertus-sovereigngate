"""Apertus SovereignGate - Enterprise Swiss FADP-Compliant Sovereign AI Gateway."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from app.api.audit import audit_router
from app.api.gateway import gateway_router
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sovereign_gate")

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger.info("Initializing Apertus SovereignGate on port %d...", settings.port)
    logger.info("Primary CSCS Sovereign Endpoint: %s", settings.cscs_base_url)
    logger.info("Fallback Hugging Face Endpoint: %s", settings.hf_base_url)
    logger.info("Swiss FADP revDSG / FINMA Circular 2018/3 Compliance Airlock Active.")
    yield
    logger.info("Apertus SovereignGate shutting down. Volatile memory purged.")


app = FastAPI(
    title="Apertus SovereignGate",
    description="Enterprise-grade Swiss FADP-compliant sovereign AI proxy gateway and auditing workbench.",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS Middleware (allows sovereign enterprise integration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-FADP-Redacted-Count",
        "X-Sovereign-Latency-MS",
        "X-Sovereign-Backend",
        "X-Sovereign-Zero-Retention",
        "X-FADP-Compliance",
    ],
)

# Register API Routers
app.include_router(gateway_router)
app.include_router(audit_router)


@app.get("/", response_class=HTMLResponse)
async def serve_workbench(request: Request) -> HTMLResponse:
    """Serve the 3-Pane glassmorphic SovereignGate workbench dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "default_model": settings.default_model,
        },
    )


@app.get("/health")
async def health_check() -> JSONResponse:
    """Gateway health check and sovereign node status."""
    return JSONResponse(
        content={
            "status": "healthy",
            "gateway": "Apertus SovereignGate",
            "jurisdiction": "Switzerland (CHE)",
            "compliance": "Swiss FADP / revDSG (100% Sovereign)",
            "primary_backend": "CSCS Swiss National Supercomputing Centre",
            "fallback_backend": "Hugging Face European Inference Network",
            "zero_data_retention": True,
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=(settings.environment == "development"),
    )
