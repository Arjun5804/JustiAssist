from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from core.dependencies import deps
from services.auth import get_current_user
from metrics import metrics
import httpx
from config import settings, OLLAMA_BASE_URL, VECTOR_STORE_PATH
from vector_store import VectorStore
from chunker import TextChunker
from data_loader import DataLoader
from services.database import User

router = APIRouter()

async def get_admin_user(user: User = Depends(get_current_user)):
    """Admin authorization dependency."""
    admin_emails = [e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
    if not admin_emails or user.email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

@router.get("/health/liveness")
async def liveness_check():
    """Cheap liveness check (process responsiveness)."""
    return {"status": "alive"}

@router.get("/health/readiness")
async def readiness_check():
    """Readiness check (PostgreSQL + VectorStore required)."""
    # Check DB (Required)
    db_status = "not_ready"
    try:
        from services.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ready"
    except Exception:
        db_status = "not_ready"

    # Check VectorStore (Required)
    vs_status = "not_ready"
    if deps.vector_store and deps.vector_store.statutory_index is not None:
        vs_status = "ready"
        
    # Check Redis (Optional, informational only)
    redis_status = "disconnected"
    try:
        from services.cache import cache
        if cache.enabled and cache.redis:
            # We use a ping but we don't await here directly if we can't easily,
            # Actually cache.redis.ping() is async.
            await cache.redis.ping()
            redis_status = "connected"
        elif not cache.enabled:
            redis_status = "disabled"
    except Exception:
        redis_status = "disconnected"

    ready = (db_status == "ready" and vs_status == "ready")
    
    response = {
        "status": "ready" if ready else "not_ready",
        "database": db_status,
        "vector_store": vs_status,
        "redis": redis_status
    }
    
    if not ready:
        return JSONResponse(status_code=503, content=response)
        
    return response

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_status = "connected" if response.status_code == 200 else "error"
    except:
        ollama_status = "disconnected"
        
    db_status = "unknown"
    try:
        from services.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected ({str(e)})"
        
    redis_status = "unknown"
    try:
        from services.cache import cache
        if cache.enabled and cache.redis:
            await cache.redis.ping()
            redis_status = "connected"
        elif not cache.enabled:
            redis_status = "disabled"
        else:
            redis_status = "disconnected"
    except Exception as e:
        redis_status = f"disconnected ({str(e)})"
    
    # We do NOT return a 503 if Redis is down, only if DB is down.
    status = "healthy" if db_status == "connected" else "unhealthy"
    
    return {
        "status": status,
        "database": db_status,
        "redis": redis_status,
        "ollama": ollama_status,
        "deps.vector_store": {
            "statutory_indexed": deps.vector_store.statutory_index is not None if deps.vector_store else False,
            "bail_indexed": deps.vector_store.bail_index is not None if deps.vector_store else False,
        }
    }


@router.get("/metrics")
async def get_metrics(user = Depends(get_admin_user)):
    """Get production metrics"""
    return metrics.get_metrics()


@router.post("/build-indices")
async def build_indices(user = Depends(get_admin_user)):
    """Trigger index building (admin endpoint)"""

    try:
        from vector_store import build_indices as _build_indices
        deps.vector_store = _build_indices()
        return {"status": "success", "message": "Indices built successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_statistics(user = Depends(get_admin_user)):
    """Get system statistics"""
    if deps.vector_store is None:
        return {"error": "Vector store not initialized"}
    
    return deps.vector_store.get_statistics()


@router.get("/api/news")
async def get_legal_news(refresh: bool = False, user = Depends(get_current_user)):
    """
    Get legal news headlines.
    
    Args:
        refresh: Force refresh from sources (bypass cache)
    """
    try:
        from services.news_scraper import get_news_scraper
        scraper = get_news_scraper()
        return scraper.get_articles_dict()
    except Exception as e:
        return {
            "articles": [],
            "error": str(e),
            "source": "error"
        }



