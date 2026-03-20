import os
import hashlib
import secrets
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship

_engine = None
_SessionLocal = None


# ─────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────

def _get_engine():
    global _engine
    if _engine is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///./modelshield.db")

        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_get_engine()
        )
    return _SessionLocal


def SessionLocal():
    return _get_session_factory()()


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String)
    google_id = Column(String, unique=True)

    credits = Column(Float, default=100.0)
    is_admin = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    api_keys = relationship("ApiKey", back_populates="user")
    usage_logs = relationship("UsageLog", back_populates="user")
    payments = relationship("Payment", back_populates="user")


# ─────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    key_prefix = Column(String, nullable=False)
    api_key_hash = Column(String, unique=True, nullable=False)

    name = Column(String, default="My API Key")
    plan = Column(String, default="free")

    rate_limit = Column(Integer, default=10)
    daily_quota = Column(Integer, default=10000)

    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")
    usage_logs = relationship("UsageLog", back_populates="api_key")


# ─────────────────────────────────────────────
# MODEL (OPENROUTER + BACKWARD SAFE)
# ─────────────────────────────────────────────

class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True)

    # 🔥 NEW: logical model (user-facing)
    logical_name = Column(String, index=True)

    # 🔥 NEW: actual provider model
    provider_model = Column(String)

    # 🔥 EXISTING compatibility
    name = Column(String, index=True)  # fallback support (old system)

    provider = Column(String, index=True)
    endpoint = Column(String)

    # routing
    priority = Column(Integer, default=1)

    # pricing + limits
    cost_per_token = Column(Float, default=0.0001)
    context_length = Column(Integer, default=4096)

    # health system (NEW)
    is_active = Column(Boolean, default=True)
    fail_count = Column(Integer, default=0)
    last_checked = Column(DateTime)

    # metadata
    description = Column(Text)


# ─────────────────────────────────────────────
# PROVIDER KEYS
# ─────────────────────────────────────────────

class ProviderKey(Base):
    __tablename__ = "provider_keys"

    id = Column(Integer, primary_key=True)

    provider = Column(String, index=True)
    api_key = Column(String, nullable=False)

    usage_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# USAGE LOG
# ─────────────────────────────────────────────

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    api_key_id = Column(Integer, ForeignKey("api_keys.id"))

    model = Column(String)

    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    tokens = Column(Integer, default=0)

    cost = Column(Float, default=0.0)

    status = Column(String, default="success")

    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="usage_logs")
    api_key = relationship("ApiKey", back_populates="usage_logs")


# ─────────────────────────────────────────────
# PAYMENT
# ─────────────────────────────────────────────

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"))

    amount = Column(Float)
    unique_amount = Column(Float)

    credits_to_add = Column(Float)

    utr = Column(String, unique=True)

    status = Column(String, default="pending")

    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime)

    user = relationship("User", back_populates="payments")


# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=_get_engine())


# ─────────────────────────────────────────────
# API KEY UTILS
# ─────────────────────────────────────────────

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return "ms_" + secrets.token_urlsafe(32)


# ─────────────────────────────────────────────
# PROVIDER KEY ROTATION (SMART + BALANCED)
# ─────────────────────────────────────────────

def get_provider_key(db, provider: str):
    keys = db.query(ProviderKey).filter(
        ProviderKey.provider == provider,
        ProviderKey.is_active == True
    ).order_by(ProviderKey.usage_count.asc()).all()

    if not keys:
        return None

    key = keys[0]
    key.usage_count += 1
    db.commit()

    return key.api_key


# ─────────────────────────────────────────────
# MODEL ROUTER (SMART + FALLBACK)
# ─────────────────────────────────────────────

def get_models_for_logical(db, logical_name: str):
    # NEW SYSTEM
    models = db.query(Model).filter(
        Model.logical_name == logical_name,
        Model.is_active == True
    ).order_by(Model.priority.asc()).all()

    # BACKWARD COMPATIBILITY
    if not models:
        models = db.query(Model).filter(
            Model.name == logical_name
        ).all()

    return models


# ─────────────────────────────────────────────
# SEED MODELS (MULTI PROVIDER)
# ─────────────────────────────────────────────

def seed_models(db):
    if db.query(Model).first():
        return

    models = [

        # 🔥 LOGICAL: llama-3.1

        Model(
            logical_name="llama-3.1",
            provider="groq",
            provider_model="llama-3.1-8b-instant",
            name="llama-3.1-8b-instant",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            priority=1
        ),

        Model(
            logical_name="llama-3.1",
            provider="nvidia",
            provider_model="meta/llama-4-maverick-17b-128e-instruct",
            name="meta/llama-4-maverick-17b-128e-instruct",
            endpoint="https://integrate.api.nvidia.com/v1/chat/completions",
            priority=2
        ),

        Model(
            logical_name="llama-3.1",
            provider="openai",
            provider_model="gpt-4o-mini",
            name="gpt-4o-mini",
            endpoint="https://api.openai.com/v1/chat/completions",
            priority=3
        ),
    ]

    for m in models:
        db.add(m)

    db.commit()


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

def seed_admin(db):
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    if not db.query(User).filter(User.email == "admin@modelshield.dev").first():
        db.add(User(
            email="admin@modelshield.dev",
            password_hash=pwd_context.hash("admin123"),
            credits=999999,
            is_admin=True
        ))
        db.commit()
