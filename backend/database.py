import os
import hashlib
import secrets
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship

# Engine and session are created lazily so DATABASE_URL env var can be set
# before first import without timing issues.
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///./modelshield.db")
        # Render gives postgres:// but SQLAlchemy needs postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        _engine = create_engine(db_url, connect_args=connect_args)
    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal


def SessionLocal():
    return _get_session_factory()()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    google_id = Column(String, nullable=True, unique=True)
    credits = Column(Float, default=100.0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_keys = relationship("ApiKey", back_populates="user")
    usage_logs = relationship("UsageLog", back_populates="user")
    payments = relationship("Payment", back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_prefix = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False, unique=True)
    name = Column(String, default="My API Key")
    plan = Column(String, default="free")
    rate_limit = Column(Integer, default=10)
    daily_quota = Column(Integer, default=10000)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="api_keys")
    usage_logs = relationship("UsageLog", back_populates="api_key")


class Model(Base):
    __tablename__ = "models"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    cost_per_token = Column(Float, default=0.0001)
    free_access = Column(Boolean, default=True)
    status = Column(String, default="active")
    description = Column(Text, default="")
    context_length = Column(Integer, default=4096)


class ProviderKey(Base):
    __tablename__ = "provider_keys"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    usage_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class UsageLog(Base):
    __tablename__ = "usage_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    status = Column(String, default="success")
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="usage_logs")
    api_key = relationship("ApiKey", back_populates="usage_logs")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    unique_amount = Column(Float, nullable=False)
    credits_to_add = Column(Float, nullable=False)
    # unique=True prevents UTR reuse fraud — a UTR can only be submitted once
    utr = Column(String, nullable=True, unique=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="payments")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables. Safe to call multiple times (idempotent)."""
    Base.metadata.create_all(bind=_get_engine())


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return "ms_" + secrets.token_urlsafe(32)


def seed_models(db):
    existing = db.query(Model).first()
    if existing:
        return
    models = [
        Model(name="llama-3.1-8b-instant", display_name="Llama 3.1 8B Instant", provider="groq",
              endpoint="https://api.groq.com/openai/v1/chat/completions",
              cost_per_token=0.00005, free_access=True, context_length=131072,
              description="Fast Llama 3.1 8B model via Groq"),
        Model(name="llama-3.1-70b-versatile", display_name="Llama 3.1 70B Versatile", provider="groq",
              endpoint="https://api.groq.com/openai/v1/chat/completions",
              cost_per_token=0.0001, free_access=False, context_length=131072,
              description="Powerful Llama 3.1 70B model via Groq"),
        Model(name="mixtral-8x7b-32768", display_name="Mixtral 8x7B", provider="groq",
              endpoint="https://api.groq.com/openai/v1/chat/completions",
              cost_per_token=0.00007, free_access=True, context_length=32768,
              description="Mixtral MoE model via Groq"),
        Model(name="gemma2-9b-it", display_name="Gemma 2 9B IT", provider="groq",
              endpoint="https://api.groq.com/openai/v1/chat/completions",
              cost_per_token=0.00005, free_access=True, context_length=8192,
              description="Google Gemma 2 9B via Groq"),
        Model(name="gpt-4o-mini", display_name="GPT-4o Mini", provider="openai",
              endpoint="https://api.openai.com/v1/chat/completions",
              cost_per_token=0.00015, free_access=False, context_length=128000,
              description="OpenAI GPT-4o Mini model"),
        Model(name="gpt-3.5-turbo", display_name="GPT-3.5 Turbo", provider="openai",
              endpoint="https://api.openai.com/v1/chat/completions",
              cost_per_token=0.0001, free_access=False, context_length=16385,
              description="OpenAI GPT-3.5 Turbo"),
        Model(name="meta/llama-3.1-8b-instruct", display_name="Llama 3.1 8B (NVIDIA)", provider="nvidia",
              endpoint="https://integrate.api.nvidia.com/v1/chat/completions",
              cost_per_token=0.00006, free_access=True, context_length=131072,
              description="Llama 3.1 8B via NVIDIA NIM"),
        Model(name="mistralai/mistral-7b-instruct-v0.3", display_name="Mistral 7B (Together)", provider="together",
              endpoint="https://api.together.xyz/v1/chat/completions",
              cost_per_token=0.00006, free_access=True, context_length=32768,
              description="Mistral 7B via Together AI"),
    ]
    for m in models:
        db.add(m)
    db.commit()


# BUG FIX: original code had email mismatch:
#   - check used: "admin@gmail.com"
#   - creation used: "admin@gamil.com"  (typo "gamil" vs "gmail")
#   - log claimed: "admin@modelshield.dev"
# All three now consistently use "admin@modelshield.dev"
def seed_admin(db):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    existing = db.query(User).filter(User.email == "admin@modelshield.dev").first()
    if not existing:
        admin = User(
            email="admin@modelshield.dev",
            password_hash=pwd_context.hash("admin123"),
            credits=999999.0,
            is_admin=True
        )
        db.add(admin)
        db.commit()
