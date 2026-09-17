from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from services.auth import SignupRequest, LoginRequest, signup_handler, login_handler, get_current_user
from core.rate_limit import RateLimiter
from config import settings

router = APIRouter()

@router.post("/api/auth/signup", dependencies=[Depends(RateLimiter("AUTH", settings.RATE_LIMIT_AUTH))])
async def auth_signup(request: SignupRequest):
    """Register a new user account"""
    result = await signup_handler(request)
    return result


@router.post("/api/auth/login", dependencies=[Depends(RateLimiter("AUTH", settings.RATE_LIMIT_AUTH))])
async def auth_login(request: LoginRequest):
    """Authenticate and get JWT token"""
    result = await login_handler(request)
    return result


@router.get("/api/auth/me")
async def auth_me(user = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {"user": user.to_dict()}


@router.post("/api/auth/sse-ticket", dependencies=[Depends(RateLimiter("SSE_TICKET", settings.RATE_LIMIT_SSE_TICKET))])
async def auth_sse_ticket(user = Depends(get_current_user)):
    """Generate a short-lived ticket for SSE stream authentication"""
    from services.auth import create_sse_ticket
    ticket = create_sse_ticket(user.id)
    return {"ticket": ticket}


