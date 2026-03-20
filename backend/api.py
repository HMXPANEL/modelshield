from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import httpx
import time

from backend.database import (
    get_db, ApiKey, User, UsageLog,
    hash_api_key, get_provider_key, get_models_for_logical
)

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
# PROVIDER CALL
# ─────────────────────────────────────────────

async def call_provider(model, payload, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(model.endpoint, json=payload, headers=headers)

    print("PROVIDER:", model.provider)
    print("STATUS:", res.status_code)
    print("RAW:", res.text)

    if res.status_code != 200:
        raise Exception(res.text)

    return res.json()


# ─────────────────────────────────────────────
# MAIN CHAT ENDPOINT (OPENROUTER CORE)
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
        raise HTTPException(400, "Model required")

    models = get_models_for_logical(db, logical_model)

    if not models:
        raise HTTPException(404, "Model not found")

    # 🔥 FALLBACK LOOP
    for m in models:
        try:
            provider_key = get_provider_key(db, m.provider)

            if not provider_key:
                continue

            payload = {
                "model": m.provider_model,
                "messages": body.get("messages", []),
                "max_tokens": body.get("max_tokens", 512),
                "temperature": body.get("temperature", 0.7),
                "top_p": body.get("top_p", 1.0)
            }

            data = await call_provider(m, payload, provider_key)

            # 💰 COST
            usage = data.get("usage") or {}
            tokens = usage.get("total_tokens", 0)
            cost = tokens * m.cost_per_token

            if user.credits < cost:
                raise HTTPException(402, "Insufficient credits")

            user.credits -= cost

            db.add(UsageLog(
                user_id=user.id,
                api_key_id=api_key.id,
                model=logical_model,
                tokens=tokens,
                cost=cost
            ))

            db.commit()

            return data

        except Exception as e:
            print("FAILED:", m.provider, str(e))
            continue

    raise HTTPException(500, "All providers failed")
