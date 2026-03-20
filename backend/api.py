import time
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import httpx

from backend.database import (
    get_db, ApiKey, User, UsageLog,
    hash_api_key, get_provider_key, get_models_for_logical
)
from backend.auth import get_current_user, get_admin_user

router = APIRouter()

MIN_REQUIRED_CREDITS = 1


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


# ─────────────────────────────────────────────
# PROVIDER CALL (ROBUST)
# ─────────────────────────────────────────────

async def call_provider(model, payload, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(model.endpoint, json=payload, headers=headers)

        print("PROVIDER:", model.provider)
        print("STATUS:", res.status_code)
        print("RAW:", res.text[:300])

        try:
            data = res.json()
        except Exception:
            raise Exception(f"Invalid JSON: {res.text}")

        if res.status_code != 200:
            raise Exception(data)

        return data

    except Exception as e:
        raise Exception(f"{model.provider} error: {str(e)}")


# ─────────────────────────────────────────────
# MAIN CHAT (OPENROUTER CORE)
# ─────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat(req: Request, db: Session = Depends(get_db)):

    # 🔐 AUTH
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

    # 💰 CREDIT CHECK
    if user.credits < MIN_REQUIRED_CREDITS:
        raise HTTPException(402, "Low credits")

    # 📦 BODY
    body = await req.json()
    logical_model = body.get("model")

    if not logical_model:
        raise HTTPException(400, "Model is required")

    # 🔥 GET ROUTED MODELS
    models = get_models_for_logical(db, logical_model)

    if not models:
        raise HTTPException(404, "Model not found")

    last_error = None

    # 🔥 FALLBACK LOOP (OPENROUTER CORE)
    for m in models:
        try:
            provider_key = get_provider_key(db, m.provider)

            if not provider_key:
                print(f"No key for provider: {m.provider}")
                continue

            payload = {
                "model": m.provider_model or m.name,  # backward support
                "messages": body.get("messages", []),
                "max_tokens": body.get("max_tokens", 512),
                "temperature": body.get("temperature", 0.7),
                "top_p": body.get("top_p", 1.0)
            }

            print(f"TRYING → {m.provider} | {payload['model']}")

            data = await call_provider(m, payload, provider_key)

            # 💰 COST CALC
            usage = data.get("usage") or {}
            tokens = usage.get("total_tokens", 0)
            cost = tokens * (m.cost_per_token or 0.0001)

            if user.credits < cost:
                raise HTTPException(402, "Insufficient credits")

            user.credits -= cost

            db.add(UsageLog(
                user_id=user.id,
                api_key_id=api_key.id,
                model=logical_model,
                tokens=tokens,
                cost=cost,
                status="success"
            ))

            db.commit()

            return data

        except Exception as e:
            print("FAILED:", m.provider, str(e))
            last_error = str(e)
            continue

    # ❌ ALL PROVIDERS FAILED
    raise HTTPException(500, f"All providers failed: {last_error}")


# ─────────────────────────────────────────────
# API KEY MANAGEMENT
# ─────────────────────────────────────────────

@router.post("/keys/create")
def create_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from backend.database import generate_api_key

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


@router.get("/keys")
def list_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).all()

    return [
        {
            "id": k.id,
            "prefix": k.key_prefix,
            "status": k.status,
            "created_at": k.created_at
        }
        for k in keys
    ]


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

@router.get("/admin/users")
def users(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return db.query(User).all()


@router.get("/admin/provider-keys")
def provider_keys(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    from backend.database import ProviderKey

    keys = db.query(ProviderKey).all()

    return [
        {
            "id": k.id,
            "provider": k.provider,
            "usage": k.usage_count,
            "active": k.is_active
        }
        for k in keys
    ]
