import os
import time
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import httpx

from backend.database import (
    get_db, User, ApiKey, Model, ProviderKey, UsageLog,
    generate_api_key, hash_api_key
)
from backend.auth import get_current_user, get_admin_user

router = APIRouter()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

UPI_ID = os.getenv("UPI_ID", "modelshield@upi")
UPI_NAME = os.getenv("UPI_NAME", "ModelShield")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # ✅ FIX

# ─────────────────────────────────────────────
# RATE LIMIT
# ─────────────────────────────────────────────

_rate_limit_store = {}

def check_rate_limit(api_key_id: int, rate_limit: int) -> bool:
    now = time.time()
    window = 60
    key = f"rl_{api_key_id}"

    if key not in _rate_limit_store:
        _rate_limit_store[key] = []

    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]

    if len(_rate_limit_store[key]) >= rate_limit:
        return False

    _rate_limit_store[key].append(now)
    return True


def get_daily_usage(db: Session, api_key_id: int) -> int:
    today = date.today()
    result = db.query(func.sum(UsageLog.tokens)).filter(
        UsageLog.api_key_id == api_key_id,
        func.date(UsageLog.timestamp) == today
    ).scalar()
    return result or 0


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    models = db.query(Model).filter(Model.status == "active").all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider": m.provider,
            "cost_per_token": m.cost_per_token,
            "free_access": m.free_access,
        }
        for m in models
    ]


# ─────────────────────────────────────────────
# API KEYS
# ─────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = "My API Key"


@router.post("/keys/create")
def create_api_key(
    req: CreateKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    count = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id,
        ApiKey.status == "active"
    ).count()

    if count >= 5:
        raise HTTPException(400, "Max 5 API keys allowed")

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    api_key = ApiKey(
        user_id=current_user.id,
        key_prefix=raw_key[:12],
        api_key_hash=key_hash
    )

    db.add(api_key)
    db.commit()

    return {"api_key": raw_key}


# ─────────────────────────────────────────────
# CHAT COMPLETION
# ─────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat(req: Request, db: Session = Depends(get_db)):

    # 🔐 USER API KEY AUTH
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")

    raw_key = auth_header.split(" ")[1]
    key_hash = hash_api_key(raw_key)

    api_key = db.query(ApiKey).filter(
        ApiKey.api_key_hash == key_hash,
        ApiKey.status == "active"
    ).first()

    if not api_key:
        raise HTTPException(401, "Invalid API key")

    user = db.query(User).filter(User.id == api_key.user_id).first()

    # 🚦 RATE LIMIT
    if not check_rate_limit(api_key.id, api_key.rate_limit):
        raise HTTPException(429, "Rate limit exceeded")

    # 📦 BODY
    body = await req.json()
    model_name = body.get("model")

    model = db.query(Model).filter(
        Model.name == model_name,
        Model.status == "active"
    ).first()

    if not model:
        raise HTTPException(404, "Model not found")

    # 🔑 PROVIDER KEY RESOLUTION (FIXED)
    provider_key = db.query(ProviderKey).filter(
        ProviderKey.provider == model.provider,
        ProviderKey.is_active == True
    ).first()

    if provider_key:
        api_key_provider = provider_key.api_key
    else:
        # fallback (for Groq)
        api_key_provider = GROQ_API_KEY

    if not api_key_provider:
        raise HTTPException(500, f"{model.provider} provider not configured")

    # 📡 PROVIDER CALL
    payload = {
        "model": model.name,
        "messages": body.get("messages", []),
    }

    headers = {
        "Authorization": f"Bearer {api_key_provider}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(model.endpoint, json=payload, headers=headers)

        if res.status_code != 200:
            raise HTTPException(res.status_code, res.text)

        data = res.json()

        # 💰 COST CALCULATION
        tokens = data.get("usage", {}).get("total_tokens", 0)
        cost = tokens * model.cost_per_token

        user.credits -= cost

        db.add(UsageLog(
            user_id=user.id,
            api_key_id=api_key.id,
            model=model.name,
            tokens=tokens,
            cost=cost
        ))

        db.commit()

        return data

    except Exception as e:
        raise HTTPException(500, f"Provider error: {str(e)}")


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

@router.get("/admin/users")
def users(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return db.query(User).all()
