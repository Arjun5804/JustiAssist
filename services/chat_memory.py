"""
JustiAssist Chat Memory Service
Persistent conversation history with save/retrieve/clear operations.
Enables context-aware follow-up questions and conversation continuity.
"""

import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from services.database import get_db_session, ChatMessage


# ==================== Core CRUD ====================

def save_message(
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
    
    Args:
        user_id: ID of the authenticated user
        role: "user" or "assistant"
        content: Message text
        conversation_id: Groups messages into a conversation thread
        query_type: legal_information, bail_related, etc.
        confidence_score: AI confidence for assistant messages
        grounding_status: pass/partial/fail for assistant messages
        agents_used: List of Native agent names that contributed
        sources_used: List of data sources (local_vectors, firecrawl, etc.)
        session_id: Document session ID if applicable
    
    Returns:
        The saved ChatMessage object
    """
    db = get_db_session()
    try:
        message = ChatMessage(
            user_id=user_id,
            role=role,
            content=content,
            conversation_id=conversation_id or str(uuid.uuid4())[:12],
            query_type=query_type,
            confidence_score=confidence_score,
            grounding_status=grounding_status,
            agents_used=json.dumps(agents_used) if agents_used else None,
            sources_used=json.dumps(sources_used) if sources_used else None,
            session_id=session_id,
            created_at=datetime.utcnow(),
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    finally:
        db.close()


def get_history(
    user_id: int,
    conversation_id: str = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Retrieve chat history for a user.
    
    Args:
        user_id: ID of the user
        conversation_id: Filter by specific conversation (optional)
        limit: Max messages to return
        offset: Pagination offset
    
    Returns:
        List of message dicts ordered by creation time
    """
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
        return [m.to_dict() for m in reversed(messages)]
    finally:
        db.close()


def get_recent_conversations(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get a list of recent distinct conversations for the user.
    
    Returns:
        List of conversation summaries with id, first message, and timestamp
    """
    db = get_db_session()
    try:
        from sqlalchemy import func, distinct

        # Get distinct conversation IDs with their latest timestamp
        conversations = (
            db.query(
                ChatMessage.conversation_id,
                func.min(ChatMessage.content).label("first_message"),
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

        return [
            {
                "conversation_id": c.conversation_id,
                "preview": c.first_message[:100] + "..." if len(c.first_message) > 100 else c.first_message,
                "last_active": c.last_active.isoformat() if c.last_active else None,
                "message_count": c.message_count,
            }
            for c in conversations
        ]
    finally:
        db.close()


def clear_history(user_id: int, conversation_id: str = None) -> int:
    """
    Clear chat history for a user.
    
    Args:
        user_id: ID of the user
        conversation_id: Clear specific conversation only (optional)
    
    Returns:
        Number of messages deleted
    """
    db = get_db_session()
    try:
        query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

        if conversation_id:
            query = query.filter(ChatMessage.conversation_id == conversation_id)

        count = query.count()
        query.delete()
        db.commit()
        return count
    finally:
        db.close()


def format_history_for_context(
    user_id: int,
    conversation_id: str = None,
    max_messages: int = 10,
    max_chars: int = 2000,
) -> str:
    """
    Format recent chat history as a context string for LLM prompts.
    Enables context-aware follow-up questions.
    
    Returns:
        Formatted string like:
        PREVIOUS CONVERSATION:
        User: What is IPC 302?
        Assistant: Section 302 of the IPC defines murder...
        User: Is this bailable?
    """
    messages = get_history(
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
