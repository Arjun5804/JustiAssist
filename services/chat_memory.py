"""
JustiAssist Chat Memory Service
Persistent conversation history with save/retrieve/clear operations.
Enables context-aware follow-up questions and conversation continuity.
"""

import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from datetime import timedelta

from services.database import get_db_session, ChatMessage
from core.exceptions import ConversationOwnershipError
from services.cache import cache


# ==================== Core CRUD ====================

async def save_message(
    user_id: int,
    role: str,
    content: str,
    conversation_id: str = None,
    query_type: str = None,
    confidence_score: float = None,
    grounding_status: str = None,
    agents_used: List[str] = None,
    sources_used: List[str] = None,
    session_id: str = None,
) -> ChatMessage:
    """
    Save a chat message to the database.
    """
    db = get_db_session()
    try:
        if conversation_id:
            # Check ownership
            existing_msg = db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).first()
            if existing_msg and existing_msg.user_id != user_id:
                raise ConversationOwnershipError(f"Conversation {conversation_id} belongs to another user")
                
            # Best-effort duplicate suppression
            if role == "user":
                recent_cutoff = datetime.utcnow() - timedelta(seconds=2)
                dup_msg = (
                    db.query(ChatMessage)
                    .filter(
                        ChatMessage.conversation_id == conversation_id,
                        ChatMessage.user_id == user_id,
                        ChatMessage.role == role,
                        ChatMessage.content == content,
                        ChatMessage.created_at >= recent_cutoff
                    )
                    .first()
                )
                if dup_msg:
                    return dup_msg

        msg_conv_id = conversation_id or str(uuid.uuid4())[:12]
        message = ChatMessage(
            user_id=user_id,
            role=role,
            content=content,
            conversation_id=msg_conv_id,
            query_type=query_type,
            confidence_score=confidence_score,
            grounding_status=grounding_status,
            agents_used=json.dumps(agents_used) if agents_used else None,
            sources_used=json.dumps(sources_used) if sources_used else None,
            session_id=session_id,
            created_at=datetime.utcnow(),
        )
        
        try:
            db.add(message)
            db.commit()
            db.refresh(message)
            
            # Phase 7E Cache invalidation (DB before cache)
            await cache.delete(f"justiassist:v1:chat:history:{user_id}:{msg_conv_id}")
            await cache.delete(f"justiassist:v1:chat:conversations:{user_id}")
            
            return message
        except Exception:
            db.rollback()
            raise
    finally:
        db.close()


async def get_history(
    user_id: int,
    conversation_id: str = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Retrieve chat history for a user.
    """
    cache_key = None
    if conversation_id and offset == 0 and limit == 20: # Only cache the standard first-page load
        cache_key = f"justiassist:v1:chat:history:{user_id}:{conversation_id}"
        cached_val = await cache.get(cache_key)
        if cached_val is not None:
            return cached_val

    db = get_db_session()
    try:
        query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

        if conversation_id:
            query = query.filter(ChatMessage.conversation_id == conversation_id)

        messages = (
            query.order_by(ChatMessage.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Return in chronological order (oldest first)
        results = [m.to_dict() for m in reversed(messages)]
        
        if cache_key:
            await cache.set(cache_key, results, ttl=3600)
            
        return results
    finally:
        db.close()


async def get_recent_conversations(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get a list of recent distinct conversations for the user.
    """
    cache_key = None
    if limit == 10:
        cache_key = f"justiassist:v1:chat:conversations:{user_id}"
        cached_val = await cache.get(cache_key)
        if cached_val is not None:
            return cached_val

    db = get_db_session()
    try:
        from sqlalchemy import func

        # Get grouped stats for recent conversations
        conversations = (
            db.query(
                ChatMessage.conversation_id,
                func.max(ChatMessage.created_at).label("last_active"),
                func.count(ChatMessage.id).label("message_count"),
            )
            .filter(
                ChatMessage.user_id == user_id,
                ChatMessage.role == "user",
            )
            .group_by(ChatMessage.conversation_id)
            .order_by(func.max(ChatMessage.created_at).desc())
            .limit(limit)
            .all()
        )

        results = []
        for c in conversations:
            # Fetch the chronological first message explicitly
            first_msg_query = (
                db.query(ChatMessage.content)
                .filter(
                    ChatMessage.conversation_id == c.conversation_id,
                    ChatMessage.user_id == user_id,
                    ChatMessage.role == "user"
                )
                .order_by(ChatMessage.created_at.asc())
                .first()
            )
            
            msg_text = first_msg_query[0] if first_msg_query else ""
            
            results.append({
                "conversation_id": c.conversation_id,
                "preview": msg_text[:100] + "..." if len(msg_text) > 100 else msg_text,
                "last_active": c.last_active.isoformat() if c.last_active else None,
                "message_count": c.message_count,
            })
            
        if cache_key:
            await cache.set(cache_key, results, ttl=900)
            
        return results
    finally:
        db.close()


async def clear_history(user_id: int, conversation_id: str = None) -> int:
    """
    Clear chat history for a user.
    """
    db = get_db_session()
    try:
        query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

        if conversation_id:
            query = query.filter(ChatMessage.conversation_id == conversation_id)

        count = query.count()
        try:
            query.delete()
            db.commit()
            
            # Invalidate cache
            if conversation_id:
                await cache.delete(f"justiassist:v1:chat:history:{user_id}:{conversation_id}")
            # we also invalidate conversations
            await cache.delete(f"justiassist:v1:chat:conversations:{user_id}")
            
            return count
        except Exception:
            db.rollback()
            raise
    finally:
        db.close()


async def format_history_for_context(
    user_id: int,
    conversation_id: str = None,
    max_messages: int = 10,
    max_chars: int = 2000,
) -> str:
    """
    Format recent chat history as a context string for LLM prompts.
    Enables context-aware follow-up questions.
    """
    messages = await get_history(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=max_messages,
    )

    if not messages:
        return ""

    lines = ["PREVIOUS CONVERSATION CONTEXT:"]
    total_chars = 0

    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]

        # Truncate long assistant messages
        if msg["role"] == "assistant" and len(content) > 500:
            content = content[:500] + "..."

        line = f"{role_label}: {content}"
        if total_chars + len(line) > max_chars:
            lines.append("... (earlier messages truncated)")
            break

        lines.append(line)
        total_chars += len(line)

    lines.append("--- END OF PREVIOUS CONVERSATION ---\n")
    return "\n".join(lines)
