import os
import time
import random
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import httpx
from database import (
    get_db, User, ApiKey, Model, ProviderKey, UsageLog, Payment,
    generate_api_key, hash_api_key
)
from auth import get_current_user, get_admin_user

router = APIRouter()

UPI_ID = os.getenv("UPI_ID", "modelshield@upi")
UPI_NAME = os.getenv("UPI_NAME", "ModelShield")

CREDIT_PACKAGES = [
    {"id": 1, "credits": 500,   "amount": 99,   "label": "Starter"},
    {"id": 2, "credits": 1500,  "amount": 249,  "label": "Pro"},
    {"id": 3, "credits": 5000,  "amount": 699,  "label": "Business"},
    {"id": 4, "credits": 15000, "amount": 1799, "label": "Enterprise"},
]

# In-memory rate limit store (per-process; resets on restart)
_rate_limit_store: dict = {}


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


# ─── Models ───────────────────────────────────────────────────────────────────

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
            "description": m.description,
            "context_length": m.context_length
        }
        for m in models
    ]


# ─── API Keys ─────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = "My API Key"


@router.post("/keys/create")
def create_api_key(req: CreateKeyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(ApiKey).filter(ApiKey.user_id == current_user.id, ApiKey.status == "active").count()
    if count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 active API keys allowed")
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    prefix = raw_key[:12]
    api_key = ApiKey(
        user_id=current_user.id,
        key_prefix=prefix,
        api_key_hash=key_hash,
        name=req.name,
        plan="free",
        rate_limit=10,
        daily_quota=10000
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return {
        "id": api_key.id,
        "key": raw_key,
        "key_prefix": prefix,
        "name": api_key.name,
        "plan": api_key.plan,
        "status": api_key.status,
        "created_at": api_key.created_at.isoformat(),
        "message": "Save this key securely. It will not be shown again."
    }


@router.get("/keys")
def list_api_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).all()
    return [
        {
            "id": k.id,
            "key_prefix": k.key_prefix + "...",
            "name": k.name,
            "plan": k.plan,
            "rate_limit": k.rate_limit,
            "daily_quota": k.daily_quota,
            "status": k.status,
            "created_at": k.created_at.isoformat()
        }
        for k in keys
    ]


@router.delete("/keys/{key_id}")
def delete_api_key(key_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.status = "revoked"
    db.commit()
    return {"message": "API key revoked successfully"}


# ─── Usage ────────────────────────────────────────────────────────────────────

@router.get("/usage")
def get_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(UsageLog).filter(UsageLog.user_id == current_user.id).order_by(UsageLog.timestamp.desc()).limit(100).all()
    total_tokens = db.query(func.sum(UsageLog.tokens)).filter(UsageLog.user_id == current_user.id).scalar() or 0
    total_cost = db.query(func.sum(UsageLog.cost)).filter(UsageLog.user_id == current_user.id).scalar() or 0.0
    return {
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "logs": [
            {
                "id": l.id,
                "model": l.model,
                "tokens": l.tokens,
                "cost": round(l.cost, 6),
                "status": l.status,
                "timestamp": l.timestamp.isoformat()
            }
            for l in logs
        ]
    }


# ─── Payments ─────────────────────────────────────────────────────────────────

class CreatePaymentRequest(BaseModel):
    package_id: int


class SubmitUTRRequest(BaseModel):
    payment_id: int
    utr: str


@router.get("/payments/packages")
def get_packages():
    return CREDIT_PACKAGES


@router.post("/payments/create")
def create_payment(req: CreatePaymentRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    package = next((p for p in CREDIT_PACKAGES if p["id"] == req.package_id), None)
    if not package:
        raise HTTPException(status_code=400, detail="Invalid package")
    unique_paise = random.randint(1, 98)
    unique_amount = round(package["amount"] + unique_paise / 100, 2)
    payment = Payment(
        user_id=current_user.id,
        amount=package["amount"],
        unique_amount=unique_amount,
        credits_to_add=package["credits"],
        status="awaiting_payment"
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    upi_link = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={unique_amount}&cu=INR&tn=ModelShield-{payment.id}"
    return {
        "payment_id": payment.id,
        "amount": unique_amount,
        "credits": package["credits"],
        "upi_id": UPI_ID,
        "upi_link": upi_link,
        "package_label": package["label"]
    }


@router.post("/payments/submit-utr")
def submit_utr(req: SubmitUTRRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.id == req.payment_id, Payment.user_id == current_user.id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Block resubmission on all non-awaiting states
    if payment.status in ("verified", "rejected", "pending_verification"):
        raise HTTPException(status_code=400, detail=f"Payment is already {payment.status}")

    utr = req.utr.strip().upper()
    if len(utr) < 6:
        raise HTTPException(status_code=400, detail="Invalid UTR number — must be at least 6 characters")

    # SECURITY: check UTR uniqueness across all payments to prevent fraud
    existing_utr = db.query(Payment).filter(Payment.utr == utr).first()
    if existing_utr:
        raise HTTPException(status_code=400, detail="This UTR has already been submitted")

    payment.utr = utr
    payment.status = "pending_verification"
    db.commit()
    return {"message": "UTR submitted. Credits will be added after admin verification."}


@router.get("/payments/status")
def payment_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payments = db.query(Payment).filter(Payment.user_id == current_user.id).order_by(Payment.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "amount": p.unique_amount,
            "credits": p.credits_to_add,
            "status": p.status,
            "utr": p.utr,
            "created_at": p.created_at.isoformat(),
            "verified_at": p.verified_at.isoformat() if p.verified_at else None
        }
        for p in payments
    ]


# ─── AI Request Gateway ───────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(req: Request, db: Session = Depends(get_db)):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    raw_key = auth_header.split(" ", 1)[1]
    key_hash = hash_api_key(raw_key)
    api_key_obj = db.query(ApiKey).filter(ApiKey.api_key_hash == key_hash, ApiKey.status == "active").first()
    if not api_key_obj:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    user = db.query(User).filter(User.id == api_key_obj.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not check_rate_limit(api_key_obj.id, api_key_obj.rate_limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")

    body = await req.json()
    model_name = body.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Model is required")

    model_obj = db.query(Model).filter(Model.name == model_name, Model.status == "active").first()
    if not model_obj:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found or inactive")

    if not model_obj.free_access and api_key_obj.plan == "free":
        if user.credits < 0.01:
            raise HTTPException(status_code=402, detail="Insufficient credits. Please buy credits.")

    daily_tokens = get_daily_usage(db, api_key_obj.id)
    if daily_tokens >= api_key_obj.daily_quota:
        raise HTTPException(status_code=429, detail="Daily token quota exceeded")

    # Prefer DB provider key, fallback to env var
    provider_key_obj = db.query(ProviderKey).filter(
        ProviderKey.provider == model_obj.provider,
        ProviderKey.is_active == True
    ).order_by(ProviderKey.usage_count).first()

    env_key_map = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "nvidia": "NVIDIA_API_KEY",
        "together": "TOGETHER_API_KEY"
    }
    provider_api_key = None
    if provider_key_obj:
        provider_api_key = provider_key_obj.api_key
    else:
        env_var = env_key_map.get(model_obj.provider)
        if env_var:
            provider_api_key = os.getenv(env_var)
    if not provider_api_key:
        raise HTTPException(status_code=503, detail=f"Provider '{model_obj.provider}' not configured")

    messages = body.get("messages")
    prompt = body.get("prompt")
    if not messages and prompt:
        messages = [{"role": "user", "content": prompt}]
    if not messages:
        raise HTTPException(status_code=400, detail="Either 'messages' or 'prompt' is required")

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": body.get("max_tokens", 1024),
        "temperature": body.get("temperature", 0.7)
    }
    headers = {
        "Authorization": f"Bearer {provider_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(model_obj.endpoint, json=payload, headers=headers)
        if response.status_code != 200:
            error_detail = response.text[:300]
            log = UsageLog(user_id=user.id, api_key_id=api_key_obj.id, model=model_name,
                           tokens=0, cost=0.0, status="error")
            db.add(log)
            db.commit()
            raise HTTPException(status_code=response.status_code, detail=f"Provider error: {error_detail}")

        result = response.json()
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        cost = total_tokens * model_obj.cost_per_token

        log = UsageLog(
            user_id=user.id,
            api_key_id=api_key_obj.id,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens=total_tokens,
            cost=cost,
            status="success"
        )
        db.add(log)
        user.credits -= cost
        if provider_key_obj:
            provider_key_obj.usage_count += 1
        db.commit()
        return result

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request to provider timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# ─── Admin Endpoints ──────────────────────────────────────────────────────────

@router.get("/admin/users")
def admin_list_users(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "credits": u.credits,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat(),
            "key_count": len(u.api_keys)
        }
        for u in users
    ]


class AddCreditsRequest(BaseModel):
    amount: float


@router.post("/admin/users/{user_id}/add-credits")
def admin_add_credits(user_id: int, data: AddCreditsRequest, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.credits += data.amount
    db.commit()
    return {"message": f"Added {data.amount} credits to {user.email}", "new_balance": user.credits}


@router.get("/admin/models")
def admin_list_models(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    models = db.query(Model).all()
    return [
        {
            "id": m.id, "name": m.name, "display_name": m.display_name,
            "provider": m.provider, "cost_per_token": m.cost_per_token,
            "free_access": m.free_access, "status": m.status,
            "context_length": m.context_length
        }
        for m in models
    ]


class ModelCreate(BaseModel):
    name: str
    display_name: str
    provider: str
    endpoint: str
    cost_per_token: float = 0.0001
    free_access: bool = True
    context_length: int = 4096
    description: str = ""


@router.post("/admin/models")
def admin_create_model(data: ModelCreate, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    model = Model(**data.dict())
    db.add(model)
    db.commit()
    db.refresh(model)
    return {"message": "Model created", "id": model.id}


# BUG FIX: was `data: dict` which FastAPI cannot auto-parse from JSON body.
# Use a proper Pydantic model with all fields optional for PATCH semantics.
class ModelUpdate(BaseModel):
    status: Optional[str] = None
    cost_per_token: Optional[float] = None
    free_access: Optional[bool] = None
    display_name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/admin/models/{model_id}")
def admin_toggle_model(model_id: int, data: ModelUpdate, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if data.status is not None:
        model.status = data.status
    if data.cost_per_token is not None:
        model.cost_per_token = data.cost_per_token
    if data.free_access is not None:
        model.free_access = data.free_access
    if data.display_name is not None:
        model.display_name = data.display_name
    if data.description is not None:
        model.description = data.description
    db.commit()
    return {"message": "Model updated"}


@router.get("/admin/provider-keys")
def admin_list_provider_keys(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    keys = db.query(ProviderKey).all()
    return [
        {
            "id": k.id,
            "provider": k.provider,
            # SECURITY: Never expose full key — only 8-char prefix
            "key_prefix": k.api_key[:8] + "..." if k.api_key else "",
            "usage_count": k.usage_count,
            "is_active": k.is_active
        }
        for k in keys
    ]


class ProviderKeyCreate(BaseModel):
    provider: str
    api_key: str


@router.post("/admin/provider-keys")
def admin_add_provider_key(data: ProviderKeyCreate, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    pk = ProviderKey(provider=data.provider, api_key=data.api_key.strip())
    db.add(pk)
    db.commit()
    return {"message": "Provider key added"}


@router.delete("/admin/provider-keys/{key_id}")
def admin_delete_provider_key(key_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    pk = db.query(ProviderKey).filter(ProviderKey.id == key_id).first()
    if not pk:
        raise HTTPException(status_code=404, detail="Provider key not found")
    db.delete(pk)
    db.commit()
    return {"message": "Provider key deleted"}


@router.get("/admin/payments")
def admin_list_payments(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "user_email": p.user.email,
            "amount": p.unique_amount,
            "credits": p.credits_to_add,
            "utr": p.utr,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
            "verified_at": p.verified_at.isoformat() if p.verified_at else None
        }
        for p in payments
    ]


@router.post("/admin/payments/{payment_id}/verify")
def admin_verify_payment(payment_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "verified":
        raise HTTPException(status_code=400, detail="Already verified")
    payment.status = "verified"
    payment.verified_at = datetime.utcnow()
    user = db.query(User).filter(User.id == payment.user_id).first()
    if user:
        user.credits += payment.credits_to_add
    db.commit()
    return {"message": f"Payment verified. {payment.credits_to_add} credits added to {user.email if user else 'user'}"}


@router.post("/admin/payments/{payment_id}/reject")
def admin_reject_payment(payment_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment.status = "rejected"
    db.commit()
    return {"message": "Payment rejected"}


@router.get("/admin/analytics")
def admin_analytics(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_tokens = db.query(func.sum(UsageLog.tokens)).scalar() or 0
    total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.status == "verified").scalar() or 0.0
    total_requests = db.query(func.count(UsageLog.id)).scalar() or 0
    model_usage = db.query(
        UsageLog.model,
        func.count(UsageLog.id).label("count"),
        func.sum(UsageLog.tokens).label("tokens")
    ).group_by(UsageLog.model).all()
    return {
        "total_users": total_users,
        "total_tokens": total_tokens,
        "total_revenue": round(total_revenue, 2),
        "total_requests": total_requests,
        "model_breakdown": [
            {"model": m, "requests": c, "tokens": t or 0}
            for m, c, t in model_usage
        ]
    }
