import sys
import typing

# Fix Python 3.13 + Pydantic v1
if sys.version_info >= (3, 13):
    from typing import ForwardRef
    def patched_evaluate(self, globalns, localns, recursive_guard=None):
        return typing._eval_type(self.__forward_arg__, globalns, localns)
    ForwardRef._evaluate = patched_evaluate

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# FIX: Import but don't call create_tables at module level yet —
# database.py uses lazy init so DATABASE_URL env var is read on first use.
# Tables are created inside lifespan so the correct DB URL is always used.
from database import create_tables, SessionLocal, seed_models, seed_admin
import auth
import api

# FIX: CORS origins configurable via env. Set ALLOWED_ORIGINS=https://yourdomain.com in .env for production.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]


# FIX: Use lifespan context manager instead of deprecated @app.on_event("startup")
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ModelShield API starting...")
    create_tables()  # idempotent — safe to call on every startup
    db = SessionLocal()
    try:
        seed_models(db)
        seed_admin(db)
        logger.info("✅ Database initialized")
        logger.info("✅ Default models seeded")
        logger.info("✅ Admin user ready: admin@modelshield.dev / admin123")
    finally:
        db.close()
    logger.info("🌐 ModelShield API running at http://localhost:8000")
    logger.info("📖 API Docs: http://localhost:8000/docs")
    logger.info("🎨 Frontend: http://localhost:8000/app")
    logger.info("🔧 Admin: http://localhost:8000/admin-panel")
    yield
    logger.info("👋 ModelShield API shutting down")


app = FastAPI(
    title="ModelShield API",
    description="AI Model Gateway - Access multiple AI providers with a single API key",
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

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
admin_path = os.path.join(os.path.dirname(__file__), "..", "admin")

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
