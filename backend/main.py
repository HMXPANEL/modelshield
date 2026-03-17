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
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

from database import create_tables, SessionLocal, seed_models, seed_admin
import auth
import api

# CORS: set ALLOWED_ORIGINS=https://yourdomain.com in .env for production
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ModelShield API starting...")
    create_tables()
    db = SessionLocal()
    try:
        seed_models(db)
        seed_admin(db)
        logger.info("✅ Database initialized")
        logger.info("✅ Default models seeded")
        logger.info("✅ Admin user ready: admin@modelshield.dev / admin123")
    finally:
        db.close()
    logger.info("🌐 ModelShield API is running")
    logger.info("📖 API Docs: /docs")
    logger.info("🎨 Frontend: /app")
    logger.info("🔧 Admin: /admin-panel")
    yield
    logger.info("👋 ModelShield API shutting down")


app = FastAPI(
    title="ModelShield API",
    description="AI Model Gateway — Access multiple AI providers with a single API key",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(api.router, tags=["API"])

# Resolve paths relative to this file so they work from any working directory
_BASE = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.normpath(os.path.join(_BASE, "..", "frontend"))
admin_path = os.path.normpath(os.path.join(_BASE, "..", "admin"))

if os.path.exists(frontend_path):
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")
if os.path.exists(admin_path):
    app.mount("/admin-panel", StaticFiles(directory=admin_path, html=True), name="admin")


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


@app.get("/health")
def health():
    return {"status": "healthy", "service": "ModelShield API"}


# BUG FIX: use app object directly instead of string "main:app" so it works
# whether launched via `python backend/main.py` or `uvicorn backend.main:app`
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
