from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from core.dependencies import deps
from services.indian_kanoon import get_kanoon_api

router = APIRouter()

@router.get("/api/kanoon/search")
async def search_indian_kanoon(
    query: str,
    page: int = 0,
    doc_type: str = "all",
):
    """
    Search Indian Kanoon for legal documents.
    
    Args:
        query: Search query (e.g., "Section 302 IPC bail")
        page: Page number (0-indexed)
        doc_type: Filter by type ('all', 'judgments', 'acts', 'sc', 'hc')
    """
    try:
        from services.indian_kanoon import get_kanoon_api
        api = get_kanoon_api()
        
        if not api.api_key:
            return {
                "error": "Indian Kanoon API key not configured",
                "hint": "Set INDIAN_KANOON_API_KEY in .env file",
                "documents": [],
                "total_results": 0,
            }
        
        results = await api.search(query, page=page, doc_type=doc_type)
        
        return {
            "query": results.query,
            "total_results": results.total_results,
            "page": results.page,
            "documents": [doc.to_dict() for doc in results.documents],
            "search_time_ms": results.search_time_ms,
        }
    except Exception as e:
        return {
            "error": str(e),
            "documents": [],
            "total_results": 0,
        }


@router.get("/api/kanoon/doc/{doc_id}")
async def get_kanoon_document(doc_id: str):
    """Get a specific document from Indian Kanoon by ID."""
    try:
        from services.indian_kanoon import get_kanoon_api
        api = get_kanoon_api()
        
        if not api.api_key:
            raise HTTPException(status_code=503, detail="Indian Kanoon API key not configured")
        
        doc = await api.get_document(doc_id)
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return doc.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


