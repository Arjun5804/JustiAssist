"""
JustiAssist v2.0 - FastAPI Web Application
Intelligent RAG & Agentic Bail Support System for Indian Legal Domain
Powered by CrewAI, Firecrawl, and Zero-Hallucination Enforcement
"""

import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

# v2.0 imports
from services.auth import (
    SignupRequest, LoginRequest, AuthResponse,
    signup_handler, login_handler,
    get_current_user, get_current_user_optional
)
from services.chat_memory import (
    save_message, get_history, get_recent_conversations,
    clear_history, format_history_for_context
)
from agents.crew_orchestrator import JustiAssistCrew, CrewResult

from config import (
    VECTOR_STORE_PATH, 
    TOP_K_STATUTORY,
    TOP_K_CASE_LAW,
    AnswerMode,
    DEFAULT_ANSWER_MODE,
    RETRIEVAL_CONFIDENCE_THRESHOLD,
    INSUFFICIENT_CONTEXT_RESPONSE,
    TOP_K_BAIL,
    GROQ_MODEL,
    OLLAMA_BASE_URL,
    log_config
)
from vector_store import VectorStore
from document_session import session_manager, get_document_context_prompt, DocumentSearchResult
from llm_provider import LLMProvider, call_llm
from agents.query_classifier import QueryClassifier, QueryType
from agents.query_reformulator import QueryReformulator
from agents.bail_evaluator import BailEvaluator
from agents.feedback_evaluator import FeedbackEvaluator, EvaluationStatus
from audit_logger import audit_logger
from metrics import metrics
from prompts.templates import (
    build_legal_prompt, 
    build_bail_prompt,
    build_prompt_with_documents,
    format_document_citation,
    UPLOADED_DOCUMENT_RULES,
    build_generation_prompt
)

from services.news_scraper import get_news_scraper
from services.pipeline_events import SyncPipelineEmitter
from reranker import LegalReranker, SearchResult as RerankSearchResult
from context_builder import ContextBuilder
from confidence_scorer import ConfidenceScorer


# Logging setup
import logging
logger = logging.getLogger(__name__)

# Global instances via deps container
from core.dependencies import deps


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    
    print("="*60)
    print("JUSTIASSIST v2.0 - Starting up...")
    print("Powered by CrewAI | Firecrawl | Zero-Hallucination Engine")
    print("="*60)
    
    # Initialize agents (legacy, still used as utilities)
    deps.query_classifier = QueryClassifier()
    deps.query_reformulator = QueryReformulator()
    deps.bail_evaluator = BailEvaluator()
    deps.feedback_evaluator = FeedbackEvaluator()
    deps.llm_provider = LLMProvider()
    
    # Initialize enhanced RAG components
    deps.reranker = LegalReranker(mode='balanced')
    deps.context_builder = ContextBuilder()
    deps.confidence_scorer = ConfidenceScorer()
    print("Enhanced RAG: reranker, context builder, confidence scorer initialized")
    
    # Load vector store
    deps.vector_store = VectorStore()
    if VECTOR_STORE_PATH.exists():
        loaded = deps.vector_store.load()
        if loaded:
            print("Vector indices loaded successfully")
        else:
            print("Warning: Could not load vector indices. Run build_indices() first.")
    else:
        print("Warning: Vector store path not found. Run build_indices() first.")
    
    # v2.0: Initialize CrewAI Orchestrator
    deps.crew_orchestrator = JustiAssistCrew(
        vector_store=deps.vector_store,
        reranker=deps.reranker,
        context_builder=deps.context_builder,
        confidence_scorer=deps.confidence_scorer,
    )
    print("CrewAI Orchestrator initialized with 5 agents")
    
    # Initialize database
    from services.database import init_db
    init_db()
    print("SQLite database initialized (users + chat history)")
    
    print("\nJustiAssist v2.0 ready!")
    print("="*60)
    
    yield
    
    # Cleanup
    print("Shutting down JustiAssist...")

app = FastAPI(
    title="JustiAssist",
    description="Intelligent RAG & Agentic Bail Support System for Indian Legal Domain",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", 
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ==================== Request/Response Models ====================
# Models and helper functions preserved for legacy compatibility

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    mode: Optional[str] = Field(default="auto", description="auto, legal, or bail")
    custody_days: Optional[int] = Field(default=None, ge=0)
    offense_sections: Optional[List[str]] = Field(default=None)
    session_id: Optional[str] = Field(default=None, description="Session ID for uploaded documents")

class Citation(BaseModel):
    section: str
    law_type: str
    text_preview: str
    source: str
    relevance_score: float

class KanoonCaseResponse(BaseModel):
    title: str
    citation: Optional[str] = None
    court: Optional[str] = None
    date: Optional[str] = None
    url: str
    preview: str = ""

class NewsContextResponse(BaseModel):
    title: str
    source: str
    date: str
    url: str = ""

class QueryResponse(BaseModel):
    query: str
    query_type: str
    answer: str
    citations: List[Citation]
    confidence_score: float
    bail_assessment: Optional[dict] = None
    grounding_status: str
    processing_info: dict
    kanoon_cases: List[KanoonCaseResponse] = []
    news_context: List[NewsContextResponse] = []
    sources_used: List[str] = []
    fetch_times_ms: dict = {}

async def generate_response(
    prompt: str,
    retrieval_scores: list = None,
    force_grounded: bool = True
) -> tuple:
    if deps.llm_provider is None:
        deps.llm_provider = LLMProvider()
    
    answer_mode = DEFAULT_ANSWER_MODE
    if retrieval_scores:
        avg_score = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0
        if avg_score < RETRIEVAL_CONFIDENCE_THRESHOLD:
            answer_mode = AnswerMode.FALLBACK
    elif retrieval_scores is not None and len(retrieval_scores) == 0:
        answer_mode = AnswerMode.FALLBACK
    
    if force_grounded:
        answer_mode = AnswerMode.GROUNDED
    
    try:
        response, mode, metadata = await deps.llm_provider.generate(
            prompt,
            answer_mode=answer_mode,
            retrieval_scores=retrieval_scores
        )
        return response, mode, metadata
    except Exception as e:
        response = await call_llm(prompt, answer_mode, retrieval_scores)
        return response, answer_mode, {"fallback": True}

def format_citations(search_results: list) -> List[Citation]:
    citations = []
    for result in search_results:
        citations.append(Citation(
            section=result.section_number,
            law_type=result.law_type,
            text_preview=result.text[:200] + "..." if len(result.text) > 200 else result.text,
            source=result.source_dataset,
            relevance_score=round(result.score, 3)
        ))
    return citations

# ==================== API Routers ====================

from api import auth, chat, query, documents, features, kanoon, admin

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(query.router)
app.include_router(documents.router)
app.include_router(features.router)
app.include_router(kanoon.router)
app.include_router(admin.router)

@app.get("/")
async def root():
    return {"message": "JustiAssist v2.0 API is running. Please access the frontend at http://localhost:3000"}
