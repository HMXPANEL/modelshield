import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel

from backend.database import get_db, User

# ─── CONFIG ─────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days

# 🚨 Hard fail if secret missing
if not SECRET_KEY:
    raise Exception("❌ SECRET_KEY not set in environment")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

router = APIRouter()

# Optional debug toggle
DEBUG_AUTH = os.getenv("DEBUG_AUTH", "false").lower() == "true"


# ─── SCHEMAS ───────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    google_id: str
    email: str


# ─── UTILS ─────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()

    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))

    to_encode.update({
        "iat": now,
        "exp": expire
    })

    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    if DEBUG_AUTH:
        print("🔐 TOKEN CREATED:", token)
        print("🔑 SECRET USED:", SECRET_KEY[:10] + "...")

    return token


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if DEBUG_AUTH:
            print("✅ TOKEN VALID")
            print("📦 PAYLOAD:", payload)

        return payload

    except JWTError as e:
        if DEBUG_AUTH:
            print("❌ JWT ERROR:", str(e))
            print("🔑 SECRET USED:", SECRET_KEY[:10] + "...")
            print("🎟 TOKEN:", token[:20] + "...")

        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ─── AUTH DEPENDENCIES ─────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:

    token = credentials.credentials

    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ─── ROUTES ───────────────────────────────────────

@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):

    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    email = req.email.strip().lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        credits=100.0
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "credits": user.credits,
            "is_admin": user.is_admin
        }
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):

    email = req.email.strip().lower()

    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "credits": user.credits,
            "is_admin": user.is_admin
        }
    }


@router.post("/google-login")
def google_login(req: GoogleLoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.google_id == req.google_id).first()

    if not user:
        email = req.email.strip().lower()

        user = db.query(User).filter(User.email == email).first()

        if user:
            user.google_id = req.google_id
        else:
            user = User(
                email=email,
                google_id=req.google_id,
                credits=100.0
            )
            db.add(user)

        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "credits": user.credits,
            "is_admin": user.is_admin
        }
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "credits": current_user.credits,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at.isoformat()
    }
