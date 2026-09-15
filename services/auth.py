"""
JustiAssist Authentication Service — JWT + bcrypt
Handles signup, login, and token validation.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
import bcrypt
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from services.database import get_db_session, User
from config import settings


# ==================== Configuration ====================

JWT_SECRET_KEY = settings.JWT_SECRET_KEY.get_secret_value()
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = settings.JWT_EXPIRY_HOURS

# Bearer token security scheme
security = HTTPBearer(auto_error=False)


# ==================== Request/Response Models ====================

class SignupRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=72)
    display_name: str = Field(..., min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ==================== Core Functions ====================

def hash_password(plain_password: str) -> str:
    """Hash a password with bcrypt (direct, no passlib)"""
    pwd_bytes = plain_password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash"""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def create_access_token(user_id: int, email: str) -> str:
    """Create a JWT access token"""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ==================== Auth Handlers ====================

async def signup_handler(request: SignupRequest) -> AuthResponse:
    """Register a new user"""
    db = get_db_session()
    try:
        # Check if email already exists
        existing = db.query(User).filter(User.email == request.email.lower()).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        user = User(
            email=request.email.lower().strip(),
            display_name=request.display_name.strip(),
            hashed_password=hash_password(request.password),
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Generate token
        token = create_access_token(user.id, user.email)

        return AuthResponse(
            access_token=token,
            user=user.to_dict()
        )
    finally:
        db.close()


async def login_handler(request: LoginRequest) -> AuthResponse:
    """Authenticate a user"""
    db = get_db_session()
    try:
        user = db.query(User).filter(User.email == request.email.lower()).first()

        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()

        # Generate token
        token = create_access_token(user.id, user.email)

        return AuthResponse(
            access_token=token,
            user=user.to_dict()
        )
    finally:
        db.close()


# ==================== Dependency Injection ====================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[User]:
    """
    FastAPI dependency: Extract and validate the current user from JWT token.
    Returns User object or raises 401.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    db = get_db_session()
    try:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()


async def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[User]:
    """
    FastAPI dependency: Extract user from JWT if present, return None otherwise.
    Used for endpoints that work both authenticated and unauthenticated.
    """
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    db = get_db_session()
    try:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        return user
    except Exception:
        return None
    finally:
        db.close()
