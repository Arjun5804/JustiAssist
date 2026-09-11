from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from services.chat_memory import get_history, get_recent_conversations, clear_history
from services.auth import get_current_user, get_current_user_optional

router = APIRouter()

@router.get("/api/chat/history")
async def get_chat_history(
    conversation_id: str = None,
    limit: int = 20,
    offset: int = 0,
    user = Depends(get_current_user_optional)
):
    """Get chat history for authenticated user"""
    if not user:
        return {"messages": [], "authenticated": False}
    
    messages = get_history(
        user_id=user.id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return {"messages": messages, "authenticated": True}


@router.get("/api/chat/conversations")
async def get_conversations(
    limit: int = 10,
    user = Depends(get_current_user_optional)
):
    """Get list of recent conversations"""
    if not user:
        return {"conversations": [], "authenticated": False}
    
    conversations = get_recent_conversations(user_id=user.id, limit=limit)
    return {"conversations": conversations, "authenticated": True}


@router.delete("/api/chat/history")
async def delete_chat_history(
    conversation_id: str = None,
    user = Depends(get_current_user)
):
    """Clear chat history (all or specific conversation)"""
    count = clear_history(user_id=user.id, conversation_id=conversation_id)
    return {"deleted": count, "message": f"Cleared {count} messages"}


