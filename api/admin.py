from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from core.dependencies import deps
from metrics import metrics
import httpx
from config import OLLAMA_BASE_URL, VECTOR_STORE_PATH
from vector_store import VectorStore
from chunker import TextChunker
from data_loader import DataLoader

router = APIRouter()

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
async def get_metrics():
    """Get production metrics"""
    return metrics.get_metrics()


@router.post("/build-indices")
async def build_indices():
    """Trigger index building (admin endpoint)"""

    try:
        from vector_store import build_indices as _build_indices
        deps.vector_store = _build_indices()
        return {"status": "success", "message": "Indices built successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_statistics():
    """Get system statistics"""
    if deps.vector_store is None:
        return {"error": "Vector store not initialized"}
    
    return deps.vector_store.get_statistics()


@router.get("/api/news")
async def get_legal_news(refresh: bool = False):
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



