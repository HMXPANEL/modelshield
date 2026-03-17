import sys
import typing

# Fix Python 3.13 + Pydantic v1 ForwardRef compatibility
if sys.version_info >= (3, 13):
    from typing import ForwardRef
    def _patched_evaluate(self, globalns, localns, recursive_guard=None):
        return typing._eval_type(self.__forward_arg__, globalns, localns)
    ForwardRef._evaluate = _patched_evaluate

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ✅ FIXED IMPORTS (CRITICAL)
from backend.database import create_tables, SessionLocal, seed_models, seed_admin
from backend import auth
from backend import api

# CORS config
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",")]
    if _raw_origins != "*"
    else ["*"]
)

# Lifespan (startup + shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ModelShield API starting...")

    try:
        create_tables()
        db = SessionLocal()

        try:
            seed_models(db)
            seed_admin(db)

            logger.info("✅ Database initialized")
            logger.info("✅ Models seeded")
            logger.info("✅ Admin ready: admin@modelshield.dev / admin123")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")

    logger.info("🌐 API running")
    logger.info("📖 Docs: /docs")

    yield

    logger.info("👋 Shutting down ModelShield API")


# Create FastAPI app
app = FastAPI(
    title="ModelShield API",
    description="AI Model Gateway — Access multiple AI providers with a single API key",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(api.router, tags=["API"])


# Static paths (safe for Render + local)
_BASE = os.path.dirname(os.path.abspath(__file__))

frontend_path = os.path.join(_BASE, "..", "frontend")
admin_path = os.path.join(_BASE, "..", "admin")

if os.path.exists(frontend_path):
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")

if os.path.exists(admin_path):
    app.mount("/admin-panel", StaticFiles(directory=admin_path, html=True), name="admin")


# Root endpoint
@app.get("/")
def root():
    return {
        "name": "ModelShield API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "frontend": "/app",
        "admin": "/admin-panel"
    }


# Health check
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ModelShield API"
    }


# Local run support
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
