"""
JustiAssist Database Models — SQLAlchemy + SQLite
User management, chat history, and audit trails.
"""

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings

# Database setup
DATABASE_URL = settings.DATABASE_URL

# Convert relative path to absolute path within project root
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////"):
    db_file = DATABASE_URL.replace("sqlite:///", "")
    db_path = Path(__file__).parent.parent / db_file
    DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==================== Models ====================

class User(Base):
    """User account model"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class ChatMessage(Base):
    """Chat message for conversation history"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    
    # Metadata for assistant messages
    query_type = Column(String(50), nullable=True)  # legal_information, bail_related
    confidence_score = Column(Float, nullable=True)
    grounding_status = Column(String(20), nullable=True)  # pass, partial, fail
    agents_used = Column(Text, nullable=True)  # JSON list of agent names
    sources_used = Column(Text, nullable=True)  # JSON list: local_vectors, firecrawl, etc.
    
    session_id = Column(String(100), nullable=True)  # Document session link
    conversation_id = Column(String(100), nullable=True, index=True)  # Groups messages into conversations

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="messages")

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "query_type": self.query_type,
            "confidence_score": self.confidence_score,
            "grounding_status": self.grounding_status,
            "agents_used": self.agents_used,
            "sources_used": self.sources_used,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==================== Database Initialization ====================

def init_db():
    """Create all tables if they don't exist"""
    Base.metadata.create_all(bind=engine)
    print("[Database] SQLite tables initialized")


def get_db():
    """Get a database session (for FastAPI dependency injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session (for direct use)"""
    return SessionLocal()


# Initialize on import
init_db()
