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

# Global instances
vector_store: VectorStore = None
query_classifier: QueryClassifier = None
query_reformulator: QueryReformulator = None
bail_evaluator: BailEvaluator = None
feedback_evaluator: FeedbackEvaluator = None
llm_provider: LLMProvider = None

# Enhanced RAG global instances
reranker: LegalReranker = None
context_builder: ContextBuilder = None
confidence_scorer: ConfidenceScorer = None

# v2.0: CrewAI Orchestrator
crew_orchestrator: JustiAssistCrew = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    global vector_store, query_classifier, query_reformulator, bail_evaluator, feedback_evaluator
    global reranker, context_builder, confidence_scorer  # Enhanced RAG
    global crew_orchestrator  # v2.0: CrewAI
    
    print("="*60)
    print("JUSTIASSIST v2.0 - Starting up...")
    print("Powered by CrewAI | Firecrawl | Zero-Hallucination Engine")
    print("="*60)
    
    # Initialize agents (legacy, still used as utilities)
    query_classifier = QueryClassifier()
    query_reformulator = QueryReformulator()
    bail_evaluator = BailEvaluator()
    feedback_evaluator = FeedbackEvaluator()
    
    # Initialize enhanced RAG components
    reranker = LegalReranker(mode='balanced')
    context_builder = ContextBuilder()
    confidence_scorer = ConfidenceScorer()
    print("Enhanced RAG: reranker, context builder, confidence scorer initialized")
    
    # Load vector store
    vector_store = VectorStore()
    if VECTOR_STORE_PATH.exists():
        loaded = vector_store.load()
        if loaded:
            print("Vector indices loaded successfully")
        else:
            print("Warning: Could not load vector indices. Run build_indices() first.")
    else:
        print("Warning: Vector store path not found. Run build_indices() first.")
    
    # v2.0: Initialize CrewAI Orchestrator
    crew_orchestrator = JustiAssistCrew(
        vector_store=vector_store,
        reranker=reranker,
        context_builder=context_builder,
        confidence_scorer=confidence_scorer,
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
    """A case from Indian Kanoon in the response"""
    title: str
    citation: Optional[str] = None
    court: Optional[str] = None
    date: Optional[str] = None
    url: str
    preview: str = ""


class NewsContextResponse(BaseModel):
    """A news item in the response"""
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
    # NEW: Hybrid retrieval fields
    kanoon_cases: List[KanoonCaseResponse] = []
    news_context: List[NewsContextResponse] = []
    sources_used: List[str] = []
    fetch_times_ms: dict = {}


# ==================== Helper Functions ====================

async def generate_response(
    prompt: str,
    retrieval_scores: list = None,
    force_grounded: bool = True
) -> tuple:
    """
    Generate LLM response with answer mode handling.
    
    Returns:
        Tuple of (response_text, answer_mode, metadata)
    """
    global llm_provider
    
    if llm_provider is None:
        llm_provider = LLMProvider()
    
    # Determine answer mode based on retrieval scores
    answer_mode = DEFAULT_ANSWER_MODE
    if retrieval_scores:
        avg_score = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0
        if avg_score < RETRIEVAL_CONFIDENCE_THRESHOLD:
            answer_mode = AnswerMode.FALLBACK
    elif retrieval_scores is not None and len(retrieval_scores) == 0:
        answer_mode = AnswerMode.FALLBACK
    
    # Force grounded mode if requested
    if force_grounded:
        answer_mode = AnswerMode.GROUNDED
    
    try:
        response, mode, metadata = await llm_provider.generate(
            prompt,
            answer_mode=answer_mode,
            retrieval_scores=retrieval_scores
        )
        return response, mode, metadata
    except Exception as e:
        # Fallback to direct call_llm
        response = await call_llm(prompt, answer_mode, retrieval_scores)
        return response, answer_mode, {"fallback": True}


def format_citations(search_results: list) -> List[Citation]:
    """Format search results as citations"""
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


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "JustiAssist v2.0 API is running. Please access the frontend at http://localhost:3000"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_status = "connected" if response.status_code == 200 else "error"
    except:
        ollama_status = "disconnected"
    
    return {
        "status": "healthy",
        "ollama": ollama_status,
        "vector_store": {
            "statutory_indexed": vector_store.statutory_index is not None if vector_store else False,
            "bail_indexed": vector_store.bail_index is not None if vector_store else False,
        }
    }


@app.get("/metrics")
async def get_metrics():
    """Get production metrics"""
    return metrics.get_metrics()


# ==================== Authentication API (v2.0) ====================

@app.post("/api/auth/signup")
async def auth_signup(request: SignupRequest):
    """Register a new user account"""
    result = await signup_handler(request)
    return result


@app.post("/api/auth/login")
async def auth_login(request: LoginRequest):
    """Authenticate and get JWT token"""
    result = await login_handler(request)
    return result


@app.get("/api/auth/me")
async def auth_me(user = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {"user": user.to_dict()}


# ==================== Chat Memory API (v2.0) ====================

@app.get("/api/chat/history")
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


@app.get("/api/chat/conversations")
async def get_conversations(
    limit: int = 10,
    user = Depends(get_current_user_optional)
):
    """Get list of recent conversations"""
    if not user:
        return {"conversations": [], "authenticated": False}
    
    conversations = get_recent_conversations(user_id=user.id, limit=limit)
    return {"conversations": conversations, "authenticated": True}


@app.delete("/api/chat/history")
async def delete_chat_history(
    conversation_id: str = None,
    user = Depends(get_current_user)
):
    """Clear chat history (all or specific conversation)"""
    count = clear_history(user_id=user.id, conversation_id=conversation_id)
    return {"deleted": count, "message": f"Cleared {count} messages"}


# ==================== CrewAI Query API (v2.0) ====================

@app.post("/api/v2/query")
async def process_query_v2(
    request: QueryRequest,
    user = Depends(get_current_user_optional)
):
    """
    v2.0 Query endpoint powered by CrewAI Orchestrator.
    
    Pipeline: ClassifierAgent → ResearcherAgent → WebIntelAgent → BailAnalystAgent → QualityReviewerAgent
    
    Features:
    - Chat memory for context-aware follow-ups
    - Firecrawl web search when local context is insufficient
    - Zero-hallucination enforcement via QualityReviewer
    - All existing functionality preserved
    """
    if vector_store is None or vector_store.statutory_index is None:
        raise HTTPException(
            status_code=503,
            detail="Vector indices not loaded. Please run the index builder first."
        )
    
    query = request.query.strip()
    
    # Get chat history for context
    chat_context = ""
    conversation_id = None
    if user:
        conversation_id = request.session_id or str(uuid.uuid4())[:12]
        chat_context = format_history_for_context(
            user_id=user.id,
            conversation_id=conversation_id,
            max_messages=6,
            max_chars=2000
        )
        # Save user message
        save_message(
            user_id=user.id,
            role="user",
            content=query,
            conversation_id=conversation_id,
            session_id=request.session_id,
        )
    
    # Get session documents if available
    session_documents = []
    if request.session_id:
        session = session_manager.get_session(request.session_id)
        if session and session.documents:
            from agents.query_reformulator import QueryReformulator
            reformulator = QueryReformulator()
            reformulated = reformulator.reformulate(query)
            doc_results = session.search(reformulated.enhanced_query, top_k=5)
            session_documents = [
                {"filename": r.filename, "text": r.text, "document_type": r.document_type, "is_statutory": False, "score": r.score}
                for r in doc_results
            ]
    
    # Run CrewAI pipeline
    result = await crew_orchestrator.process_query(
        query=query,
        mode=request.mode,
        chat_history=chat_context,
        session_documents=session_documents,
        custody_days=request.custody_days,
        offense_sections=request.offense_sections,
        session_id=request.session_id,
    )
    
    # Save assistant response to chat memory
    if user:
        save_message(
            user_id=user.id,
            role="assistant",
            content=result.answer,
            conversation_id=conversation_id,
            query_type=result.query_type.value if hasattr(result.query_type, 'value') else result.query_type,
            confidence_score=result.confidence_score,
            grounding_status=result.grounding_status,
            agents_used=result.agents_used,
            sources_used=result.sources_used,
            session_id=request.session_id,
        )
    
    return result.to_response_dict()


# ==================== SSE Stream v2.0 ====================

@app.get("/api/v2/query/stream")
async def query_stream_v2(
    query: str,
    mode: str = "auto",
    session_id: str = None,
    custody_days: int = None,
    offense_sections: List[str] = None,
    token: str = None,
    header_user = Depends(get_current_user_optional),
):
    """
    v2.0 SSE Stream — Real-time pipeline updates via CrewAI orchestrator.
    """
    import json
    from services.auth import decode_token
    from services.database import get_db_session, User
    
    # Resolve user (EventSource uses query token, standard fetch uses header)
    user = header_user
    if not user and token:
        payload = decode_token(token)
        if payload:
            db = get_db_session()
            user = db.query(User).filter(User.id == int(payload["sub"])).first()
            db.close()
            
    async def event_generator():
        try:
            # Get chat context
            chat_context = ""
            conversation_id = None
            if user:
                conversation_id = session_id or str(uuid.uuid4())[:12]
                chat_context = format_history_for_context(
                    user_id=user.id, conversation_id=conversation_id
                )
                save_message(user_id=user.id, role="user", content=query, conversation_id=conversation_id, session_id=session_id)
            
            # Stage callback for SSE
            def on_stage(stage, status, data=None):
                pass  # Collected in emit list
            
            stage_events = []
            def emit_stage(stage, status, data=None):
                stage_events.append({"stage": stage, "status": status, "data": data})
            
            # Get session documents if available
            session_documents = []
            if session_id:
                session = session_manager.get_session(session_id)
                if session and session.documents:
                    from agents.query_reformulator import QueryReformulator
                    reformulator = QueryReformulator()
                    reformulated = reformulator.reformulate(query)
                    doc_results = session.search(reformulated.enhanced_query, top_k=5)
                    session_documents = [
                        {"filename": r.filename, "text": r.text, "document_type": r.document_type, "is_statutory": False, "score": r.score}
                        for r in doc_results
                    ]
            
            # Run crew pipeline
            result = await crew_orchestrator.process_query(
                query=query,
                mode=mode,
                chat_history=chat_context,
                session_documents=session_documents,
                custody_days=custody_days,
                offense_sections=offense_sections or [],
                session_id=session_id,
                on_stage=emit_stage,
            )
            
            # Emit all stage events
            for evt in stage_events:
                yield f"data: {json.dumps({'type': 'stage', 'stage': evt['stage'], 'status': evt['status'], 'data': evt.get('data')})}\n\n"
            
            # Save response
            if user:
                save_message(
                    user_id=user.id, role="assistant", content=result.answer,
                    conversation_id=conversation_id, query_type=result.query_type.value if hasattr(result.query_type, 'value') else result.query_type,
                    confidence_score=result.confidence_score,
                    grounding_status=result.grounding_status,
                    agents_used=result.agents_used, sources_used=result.sources_used,
                    session_id=session_id
                )
            
            # Final result
            yield f"data: {json.dumps({'type': 'complete', 'data': {'response': result.to_response_dict()}})}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ==================== Legacy Endpoints (preserved for compatibility) ====================

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a legal or bail query with ENHANCED RETRIEVAL.
    
    Flow:
    1. Classify query type
    2. Reformulate with legal terminology expansion
    3. Two-stage retrieval (semantic + reranking)
    4. Structured context building
    5. Multi-factor confidence scoring
    6. GPT-4 fallback if needed (with transparency)
    """
    
    if vector_store is None or vector_store.statutory_index is None:
        raise HTTPException(
            status_code=503, 
            detail="Vector indices not loaded. Please run the index builder first."
        )
    
    query = request.query.strip()
    query_id = str(uuid.uuid4())
    processing_info = {"steps": [], "enhanced_rag": True, "query_id": query_id}
    
    # Metrics: Start tracking
    start_time = datetime.utcnow()
    metrics.incr("queries_total")
    
    # Step 1: Classify query
    if request.mode == "auto":
        classification = await query_classifier.classify(query)
        query_type = classification.query_type
        if query_type == QueryType.BAIL_QUERY:
            metrics.incr("queries_bail")
        elif query_type == QueryType.LEGAL_INFO:
            metrics.incr("queries_legal")
        processing_info["steps"].append(f"✓ Classified as: {query_type.value}")
    elif request.mode == "bail":
        query_type = QueryType.BAIL_QUERY
    else:
        query_type = QueryType.LEGAL_INFO
    
    # Step 2: ENHANCED Reformulation
    reformulated = query_reformulator.reformulate(query)
    requested_sections = reformulated.extracted_sections
    processing_info["steps"].append(
        f"✓ Query enhanced: {len(reformulated.search_terms)} terms, "
        f"{len(requested_sections)} sections detected"
    )
    print(f"[ENHANCED REFORMULATION] Sections: {requested_sections}")
    print(f"[ENHANCED REFORMULATION] Enhanced query: {reformulated.enhanced_query}")
    
    # Step 2.5: CHECK FOR SESSION DOCUMENTS (if session_id provided)
    session_documents = []
    doc_search_results = []
    if request.session_id:
        session = session_manager.get_session(request.session_id)
        if session and session.documents:
            # Search the session's documents for relevant chunks
            doc_search_results = session.search(reformulated.enhanced_query, top_k=5)
            session_documents = [
                {
                    "filename": r.filename,
                    "text": r.text,
                    "document_type": r.document_type,
                    "is_statutory": False,
                    "score": r.score
                }
                for r in doc_search_results
            ]
            processing_info["steps"].append(f"✓ Retrieved {len(session_documents)} chunks from uploaded documents")
            print(f"[SESSION DOCS] Found {len(session_documents)} document chunks for session {request.session_id}")
    
    # Step 3: TWO-STAGE RETRIEVAL WITH HYBRID SEARCH
    # Stage 1: Hybrid search (BM25 + semantic) for better section matching
    initial_results = vector_store.hybrid_search_statutory(
        reformulated.enhanced_query,
        top_k=TOP_K_STATUTORY * 3,  # Over-retrieve for reranking
        semantic_weight=0.6,
        bm25_weight=0.4
    )
    
    processing_info["steps"].append(f"✓ Hybrid search retrieved {len(initial_results)} candidates")
    
    # Stage 2: RERANK with legal-specific signals
    if initial_results:
        # Convert to reranker format
        rerank_results = []
        for r in initial_results:
            rerank_results.append(RerankSearchResult(
                chunk_id=r.chunk_id,
                text=r.text,
                score=r.score,
                law_type=r.law_type,
                section_number=r.section_number,
                source_dataset=r.source_dataset,
                dataset_type=r.dataset_type,
                metadata=r.metadata
            ))
        
        # Determine reranking mode
        if requested_sections:
            rerank_mode = 'precision'  # Section-specific query
        else:
            rerank_mode = 'balanced'  # General query
        
        # Apply reranker
        statutory_results = reranker.rerank(
            results=rerank_results,
            requested_sections=requested_sections,
            extracted_law_types=reformulated.extracted_law_types,
            top_k=TOP_K_STATUTORY,
            mode=rerank_mode
        )
        
        processing_info["steps"].append(
            f"✓ Reranked with {rerank_mode} mode → {len(statutory_results)} top results"
        )
        
        # Log reranking details
        print(f"\n{'='*60}")
        print(f"[RERANKING DEBUG] Mode: {rerank_mode}")
        print(f"[RERANKING DEBUG] Top-3 scores:")
        for i, r in enumerate(statutory_results[:3], 1):
            scores = r.metadata.get('reranking_scores', {})
            print(f"  {i}. {r.section_number} - Final: {r.score:.3f} "
                  f"(Statute: {scores.get('statute_presence', 0):.2f}, "
                  f"Match: {scores.get('section_match', 0):.2f})")
        print(f"{'='*60}\n")
    else:
        statutory_results = []
        processing_info["steps"].append("⚠ No results from initial retrieval")
    
    # Retrieve case law if bail query
    bail_results = []
    if query_type == QueryType.BAIL_QUERY:
        initial_case_law = vector_store.search_case_law(
            reformulated.enhanced_query,
            top_k=TOP_K_CASE_LAW * 2  # Over-retrieve
        )
        
        # Rerank case law (less aggressive, focus on semantic)
        if initial_case_law:
            rerank_case_law = [
                RerankSearchResult(
                    chunk_id=r.chunk_id, text=r.text, score=r.score,
                    law_type=r.law_type, section_number=r.section_number,
                    source_dataset=r.source_dataset, dataset_type=r.dataset_type,
                    metadata=r.metadata
                ) for r in initial_case_law
            ]
            bail_results = reranker.rerank(
                results=rerank_case_law,
                requested_sections=[],
                top_k=TOP_K_CASE_LAW,
                mode='recall'  # Less aggressive for case law
            )
        
        processing_info["steps"].append(f"✓ Retrieved {len(bail_results)} case law precedents")
    
    # Step 4: STRUCTURED CONTEXT BUILDING
    structured_context_text = context_builder.build_structured_context(
        statutory_results=statutory_results,
        case_law_results=bail_results if bail_results else None,
        uploaded_docs=session_documents if 'session_documents' in locals() else None,
        max_tokens=3000
    )
    
    processing_info["steps"].append("✓ Built structured, evidence-aware context")
    
    # Step 5: MULTI-FACTOR CONFIDENCE SCORING
    retrieval_confidence = confidence_scorer.compute_confidence(
        query=query,
        reformulated_query=reformulated,
        results=statutory_results,
        query_type=query_type.value
    )
    
    processing_info["confidence_breakdown"] = retrieval_confidence.to_dict()
    processing_info["steps"].append(
        f"✓ Confidence: {retrieval_confidence.overall_score:.2f} ({retrieval_confidence.get_label()})"
    )
    
    # Step 6: DETERMINE RESPONSE MODE (Tiered Confidence)
    from config import ConfidenceLevel, FALLBACK_LABELS
    
    confidence_level, confidence_reason = confidence_scorer.get_response_mode(retrieval_confidence)
    processing_info["confidence_level"] = confidence_level.value
    processing_info["confidence_reason"] = confidence_reason
    
    # Determine grounding mode based on confidence level
    # Values match frontend ResponseCard.jsx expectations: 'pass', 'partial', 'fail'
    if confidence_level == ConfidenceLevel.HIGH:
        grounding_status = "pass"
        use_fallback = False
        fallback_label = None
    elif confidence_level == ConfidenceLevel.MEDIUM:
        grounding_status = "partial"
        use_fallback = False
        fallback_label = None
    else:  # LOW or VERY_LOW
        grounding_status = "fail"
        use_fallback = True
        fallback_label = FALLBACK_LABELS.get(confidence_level, FALLBACK_LABELS[ConfidenceLevel.LOW])
    
    processing_info["grounding_status"] = grounding_status
    
    # OBS: Log retrieval event
    audit_logger.log_retrieval(
        query_id=query_id,
        query_text=query,
        reformulated_query=reformulated.enhanced_query,
        results=statutory_results,
        confidence_score=retrieval_confidence.overall_score,
        confidence_level=confidence_level.value,
        search_type="hybrid"
    )
    
    # OBS: Update retrieval metrics
    metrics.observe("retrieval_scores", retrieval_confidence.overall_score)
    metrics.incr(f"confidence_{confidence_level.value}")
    if statutory_results:
        metrics.incr("retrieval_hits")
    
    # Step 7: GENERATE ANSWER
    bail_assessment = None
    
    if query_type == QueryType.BAIL_QUERY:
        # Build statutory context list
        statutory_context_list = [
            {
                "section_number": r.section_number,
                "law_type": r.law_type,
                "text": r.text,
                "source": r.source_dataset
            }
            for r in statutory_results
        ]
        
        bail_context_list = [
            {
                "section_number": r.section_number,
                "law_type": r.law_type,
                "text": r.text,
                "metadata": r.metadata
            }
            for r in bail_results
        ]
        
        # If session documents are available, use document-aware prompt
        if session_documents:
            # Use LLM with document-aware prompt instead of rule-based evaluator
            prompt = build_prompt_with_documents(
                query=query,
                statutory_context=statutory_context_list,
                document_context=session_documents,
                bail_context=bail_context_list,
                is_bail_query=True
            )
            
            answer = await call_llm(prompt)
            confidence_score = 0.85  # High confidence when document is available
            
            # Create assessment from document analysis (matching frontend structure)
            bail_assessment = {
                "bail_likelihood": "Document Analysis",
                "legal_reasoning": {
                    "bailable_status": "See document for court decision",
                    "max_punishment": "See document sections",
                    "severity_score": 0,
                    "applicable_crpc": ["Analysis based on uploaded document"]
                },
                "explanation": "Analysis based on uploaded court document/FIR."
            }
            processing_info["steps"].append("✓ Document-aware bail analysis completed")
        else:
            # No documents - use rule-based evaluator
            evaluation = await bail_evaluator.evaluate(
                query=query,
                statutory_context=statutory_context_list,
                bail_precedents=bail_context_list,
                custody_duration_days=request.custody_days,
                offence_sections=request.offense_sections
            )
            
            answer = evaluation.explanation
            confidence_score = evaluation.confidence_score
            bail_assessment = evaluation.to_dict()
            processing_info["steps"].append("✓ Bail evaluation completed")
        
    else:
        # Regular legal query - build prompt with structured context
        prompt = f"""You are JustiAssist, an AI legal assistant for Indian criminal law.

{'='*60}
ANSWER MODE: {grounding_status}
{'='*60}

USER QUERY: {query}

{'='*60}
RETRIEVED LEGAL CONTEXT (Structured by Evidence Type):
{'='*60}

{structured_context_text}

{'='*60}
INSTRUCTIONS:
{'='*60}

"""
        
        if use_fallback:
            # GPT-4 FALLBACK MODE — keep answer clean, UI handles trust signals
            prompt += f"""
FALLBACK MODE — The retrieved context is limited.
Reason: {confidence_reason}

You may use your general legal knowledge to answer this query.
1. Provide the best answer you can based on your training
2. If possible, mention which legal provisions are relevant (cite section numbers)
3. Structure your answer clearly
4. Do NOT add warnings, disclaimers or notes about insufficient context — the UI handles that separately
"""
        else:
            # GROUNDED MODE (High Confidence)
            prompt += """
✓ GROUNDED MODE (High Retrieval Confidence)

Answer ONLY from the retrieved legal context above:
1. Cite exact section numbers for every legal claim
2. Use direct quotes from the context when possible
3. If the context doesn't contain sufficient information, say so explicitly
4. Do NOT fabricate or assume legal provisions not in the context
5. Structure your answer clearly with relevant sections cited

CRITICAL: Every legal provision you mention MUST appear in the context above.
"""
        
        # Call LLM with our custom prompt
        answer = await call_llm(prompt, temperature=0.3, max_tokens=2000)
        
        # Note: Fallback label is NOT prepended to the answer text.
        # The frontend displays grounding_status and confidence badges instead,
        # keeping the answer text clean and readable.
        
        # Adjust confidence based on grounding status
        if use_fallback:
            confidence_score = 0.4  # Lower for fallback
            processing_info["steps"].append(f"⚠ GPT-4 fallback mode used ({confidence_level.value} confidence)")
        else:
            confidence_score = 0.75 + (retrieval_confidence.overall_score * 0.2)  # Boost if high confidence
            processing_info["steps"].append(f"✓ Grounded answer generated ({confidence_level.value} confidence)")
    
    # Step 8: Citation Validation (pre-response check)
    from citation_validator import citation_validator
    
    all_context = [{
        "section_number": r.section_number,
        "law_type": r.law_type,
        "text": r.text
    } for r in (statutory_results + bail_results)]
    
    citation_validation = citation_validator.validate(
        response=answer,
        context_chunks=all_context,
        strict=False
    )
    
    if not citation_validation.is_valid:
        print(f"[CITATION WARNING] Invalid sections: {citation_validation.invalid_sections}")
        processing_info["citation_warning"] = True
        processing_info["invalid_citations"] = citation_validation.invalid_sections
        
        # Sanitize response with warning
        answer = citation_validator.sanitize_response(answer, citation_validation)
        confidence_score = max(confidence_score - 0.15, 0.3)  # Penalize score
    
    processing_info["steps"].append(
        f"✓ Citation validation: {len(citation_validation.valid_sections)}/{len(citation_validation.cited_sections)} verified"
    )
    
    # Step 9: Final Grounding Evaluation
    grounding_eval = feedback_evaluator.evaluate(answer, all_context, query)
    
    # Adjust confidence based on grounding evaluation
    if grounding_eval.grounding_score > 0.7:
        confidence_score = min(confidence_score + 0.1, 0.95)
    elif grounding_eval.grounding_score < 0.5 and not use_fallback:
        # If grounded mode but poor grounding, flag it
        confidence_score = max(confidence_score - 0.15, 0.3)
    
    processing_info["steps"].append(f"✓ Grounding evaluation: {grounding_eval.grounding_score:.2f}")
    processing_info["grounding_details"] = grounding_eval.to_dict()
    
    # Format citations
    all_results = statutory_results + bail_results
    citations = format_citations(all_results)
    
    # OBS: Log generation event
    latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    audit_logger.log_generation(
        query_id=query_id,
        grounding_mode=grounding_status,
        response=answer,
        citations_valid=len(citation_validation.valid_sections),
        citations_invalid=len(citation_validation.invalid_sections),
        fabrication_score=citation_validation.fabrication_score,
        llm_model=GROQ_MODEL,
        latency_ms=latency_ms
    )
    
    # OBS: Update response metrics
    metrics.observe("latency_ms", latency_ms)
    metrics.observe("citation_validity", 1.0 - citation_validation.fabrication_score)
    if citation_validation.invalid_sections:
        metrics.incr("citation_warnings")
    
    if use_fallback:
        metrics.incr("responses_fallback")
    else:
        metrics.incr("responses_grounded")
    
    # Step 10: HYBRID RETRIEVAL - Fetch from Indian Kanoon and News (parallel, non-blocking)
    kanoon_cases = []
    news_context = []
    sources_used = ["local_vectors"]
    fetch_times_ms = {}
    
    try:
        from services.indian_kanoon import get_kanoon_api
        from services.news_scraper import get_news_scraper
        
        # Build search query from reformulated sections
        search_sections = requested_sections if requested_sections else []
        kanoon_query = " ".join(search_sections[:2]) + " bail judgment" if search_sections else query[:50]
        
        # Parallel fetch with timeouts
        async def fetch_kanoon():
            try:
                api = get_kanoon_api()
                if api.api_key:
                    import time
                    start = time.time()
                    result = await asyncio.wait_for(
                        api.search(kanoon_query, doc_type="judgments"),
                        timeout=3.0
                    )
                    elapsed = int((time.time() - start) * 1000)
                    return [{
                        "title": d.title,
                        "citation": d.citation,
                        "court": d.court,
                        "date": d.date,
                        "url": d.url,
                        "preview": (d.headline or "")[:150]
                    } for d in result.documents[:3]], elapsed
            except Exception as e:
                print(f"[HYBRID] Kanoon fetch error: {e}")
            return [], 0
        
        async def fetch_news():
            try:
                scraper = get_news_scraper()
                news_query = " ".join(search_sections[:2]) + " India law" if search_sections else "Indian law " + query[:30]
                import time
                start = time.time()
                articles = await asyncio.to_thread(scraper.get_news, news_query)
                elapsed = int((time.time() - start) * 1000)
                return [{
                    "title": a.get("title", ""),
                    "source": a.get("source", "Unknown"),
                    "date": a.get("published date", ""),
                    "url": a.get("url", "")
                } for a in articles[:2]], elapsed
            except Exception as e:
                print(f"[HYBRID] News fetch error: {e}")
            return [], 0
        
        # Run both in parallel
        kanoon_result, news_result = await asyncio.gather(fetch_kanoon(), fetch_news())
        
        if kanoon_result[0]:
            kanoon_cases = kanoon_result[0]
            sources_used.append("indian_kanoon")
            fetch_times_ms["kanoon"] = kanoon_result[1]
            processing_info["steps"].append(f"✓ Found {len(kanoon_cases)} relevant cases from Indian Kanoon")
        
        if news_result[0]:
            news_context = news_result[0]
            sources_used.append("legal_news")
            fetch_times_ms["news"] = news_result[1]
            processing_info["steps"].append(f"✓ Found {len(news_context)} relevant news articles")
    
    except Exception as e:
        print(f"[HYBRID] Overall error: {e}")
    
    # Return response with hybrid data
    return QueryResponse(
        query=query,
        query_type=query_type.value,
        answer=answer,
        citations=citations,
        confidence_score=round(confidence_score, 2),
        bail_assessment=bail_assessment,
        grounding_status=grounding_status,
        processing_info=processing_info,
        kanoon_cases=kanoon_cases,
        news_context=news_context,
        sources_used=sources_used,
        fetch_times_ms=fetch_times_ms
    )


@app.get("/stats")
async def get_statistics():
    """Get system statistics"""
    if vector_store is None:
        return {"error": "Vector store not initialized"}
    
    return vector_store.get_statistics()


@app.post("/build-indices")
async def build_indices():
    """Trigger index building (admin endpoint)"""
    global vector_store
    
    try:
        from vector_store import build_indices as _build_indices
        vector_store = _build_indices()
        return {"status": "success", "message": "Indices built successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== News API ====================

@app.get("/api/news")
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



# ==================== CasePredictAI ====================

class CasePredictionRequest(BaseModel):
    """Request model for AI case outcome prediction"""
    case_type: str = Field(..., description="criminal, civil, constitutional, family, property")
    sections_involved: List[str] = Field(default_factory=list)
    case_facts: str = Field(..., min_length=20)
    court_level: str = Field(default="sessions", description="district, sessions, high_court, supreme_court")
    jurisdiction: str = Field(default="Delhi")
    prior_proceedings: Optional[str] = None
    client_role: str = Field(default="accused", description="petitioner, respondent, accused, complainant")


@app.post("/api/predict/case")
async def predict_case_outcome(request: CasePredictionRequest):
    """
    CasePredictAI — Predict case outcome with multiple strategic approaches.
    Uses LLM with retrieved legal context for grounded predictions.
    """
    try:
        import json as json_module

        # Step 1: Retrieve relevant statutory context for grounding
        sections_query = " ".join(request.sections_involved[:5]) if request.sections_involved else ""
        search_query = f"{request.case_type} {sections_query} {request.case_facts[:200]}"

        statutory_context = ""
        if vector_store and vector_store.statutory_index is not None:
            results = vector_store.hybrid_search_statutory(
                search_query,
                top_k=8,
                semantic_weight=0.6,
                bm25_weight=0.4
            )
            if results:
                statutory_context = "\n\n".join([
                    f"**{r.section_number}** ({r.law_type}): {r.text[:300]}"
                    for r in results[:6]
                ])

        # Step 2: Build prediction prompt
        prediction_prompt = f"""You are CasePredictAI, an advanced legal prediction assistant specialized in Indian law.

TASK: Analyze the following case and provide a detailed prediction with multiple strategic approaches.

CASE DETAILS:
- Case Type: {request.case_type}
- Sections Involved: {', '.join(request.sections_involved) if request.sections_involved else 'Not specified'}
- Court Level: {request.court_level}
- Jurisdiction: {request.jurisdiction}
- Client Role: {request.client_role}
- Prior Proceedings: {request.prior_proceedings or 'None'}

CASE FACTS:
{request.case_facts}

RELEVANT LEGAL PROVISIONS:
{statutory_context if statutory_context else 'No specific provisions retrieved — use general legal knowledge.'}

INSTRUCTIONS — Respond in VALID JSON format ONLY (no markdown, no code fences):

{{
  "outcome_prediction": {{
    "favorable_percentage": <number 0-100>,
    "unfavorable_percentage": <number 0-100>,
    "settlement_percentage": <number 0-100>,
    "summary": "<2-3 sentence overall prediction>",
    "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
  }},
  "strategies": [
    {{
      "name": "Aggressive",
      "approach": "<detailed strategy description, 3-4 sentences>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }},
    {{
      "name": "Balanced",
      "approach": "<detailed strategy description>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }},
    {{
      "name": "Conservative",
      "approach": "<detailed strategy description>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }}
  ],
  "risk_factors": [
    {{
      "risk": "<risk description>",
      "severity": "high/medium/low",
      "mitigation": "<how to mitigate>"
    }}
  ],
  "relevant_provisions": [
    {{
      "section": "<section number>",
      "law": "<act name>",
      "relevance": "<why relevant>"
    }}
  ],
  "precedent_cases": [
    {{
      "case_name": "<case name>",
      "citation": "<citation if known>",
      "relevance": "<how it applies>"
    }}
  ],
  "timeline_estimate": "<estimated duration>",
  "confidence_score": <number 0.0 to 1.0>
}}

Be thorough, specific to Indian law, and grounded in the legal provisions provided where possible.
"""

        # Step 3: Call LLM
        raw_text = await call_llm(prediction_prompt, temperature=0.4, max_tokens=3000)
        raw_text = raw_text.strip()

        # Parse JSON from response (strip markdown fences if present)
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

        prediction = json_module.loads(raw_text)

        return {
            "status": "success",
            "prediction": prediction,
            "grounded": bool(statutory_context),
            "sections_retrieved": len(statutory_context.split("**")) - 1 if statutory_context else 0
        }

    except Exception as e:
        print(f"[CasePredictAI] Error: {e}")
        # Return demo prediction
        return {
            "status": "demo",
            "prediction": _get_demo_prediction(request),
            "grounded": False,
            "sections_retrieved": 0,
            "note": "Demo prediction — AI service temporarily unavailable"
        }


def _get_demo_prediction(request: CasePredictionRequest) -> dict:
    """Generate a structured demo prediction when LLM is unavailable"""
    sections_text = ', '.join(request.sections_involved) if request.sections_involved else 'General provisions'
    return {
        "outcome_prediction": {
            "favorable_percentage": 55,
            "unfavorable_percentage": 30,
            "settlement_percentage": 15,
            "summary": f"Based on the {request.case_type} case involving {sections_text} at the {request.court_level} level, the case presents moderate prospects. The strength of evidence and applicable legal provisions will be decisive factors.",
            "key_factors": [
                "Strength of documentary evidence",
                f"Applicable provisions under {sections_text}",
                "Judicial precedents in similar matters",
                f"Current judicial trends in {request.jurisdiction}"
            ]
        },
        "strategies": [
            {
                "name": "Aggressive",
                "approach": f"Pursue an aggressive litigation strategy by challenging the opposing party's claims head-on. File preliminary applications to establish procedural advantage and seek early hearing dates. Leverage strong constitutional arguments and recent progressive judgments.",
                "pros": ["Can lead to early resolution", "Shows strength of conviction", "May pressure opposing party"],
                "cons": ["Higher litigation costs", "Risk of adverse costs order", "May antagonize the bench"],
                "success_rate": "45%",
                "recommended_actions": [
                    "File preliminary objections immediately",
                    "Seek urgent interim relief",
                    "Compile comprehensive case law compilation"
                ]
            },
            {
                "name": "Balanced",
                "approach": f"Adopt a measured approach that combines strong legal arguments with openness to mediation. Present the case methodically while exploring settlement possibilities through court-annexed mediation. This preserves all legal options while demonstrating reasonableness.",
                "pros": ["Maintains judicial goodwill", "Preserves all options", "Cost-effective in the long run"],
                "cons": ["May take longer to resolve", "Could be perceived as indecisive"],
                "success_rate": "60%",
                "recommended_actions": [
                    "File well-researched written submissions",
                    "Express willingness for mediation",
                    "Prepare expert witness depositions"
                ]
            },
            {
                "name": "Conservative",
                "approach": f"Focus on settlement negotiations and alternative dispute resolution. Engage the opposing party through structured dialogue and seek a mutually acceptable resolution. Use the threat of prolonged litigation as leverage while keeping the door open for compromise.",
                "pros": ["Lowest litigation risk", "Preserves relationships", "Faster resolution possible"],
                "cons": ["May result in less favorable terms", "Could be seen as weakness"],
                "success_rate": "70%",
                "recommended_actions": [
                    "Initiate pre-litigation mediation",
                    "Prepare settlement term sheet",
                    "Engage senior counsel for negotiations"
                ]
            }
        ],
        "risk_factors": [
            {"risk": "Delay in judicial proceedings", "severity": "medium", "mitigation": "File applications for expedited hearing"},
            {"risk": "Adverse interpretation of key provisions", "severity": "high", "mitigation": "Prepare comprehensive legal brief with supporting precedents"},
            {"risk": "Evidentiary challenges", "severity": "medium", "mitigation": "Secure documentary evidence and affidavits early"},
            {"risk": "Cost escalation", "severity": "low", "mitigation": "Set litigation budget with periodic review"}
        ],
        "relevant_provisions": [
            {"section": sections_text.split(",")[0] if request.sections_involved else "General", "law": "Indian Penal Code / Bharatiya Nyaya Sanhita", "relevance": "Primary substantive law applicable to the case"},
            {"section": "Section 482 CrPC (Section 528 BNSS)", "law": "Code of Criminal Procedure / BNSS", "relevance": "Inherent powers of High Court for quashing"},
            {"section": "Article 21", "law": "Constitution of India", "relevance": "Fundamental right to life and personal liberty"}
        ],
        "precedent_cases": [
            {"case_name": "Arnesh Kumar v. State of Bihar", "citation": "(2014) 8 SCC 273", "relevance": "Guidelines on arrest procedures and personal liberty"},
            {"case_name": "Satender Kumar Antil v. CBI", "citation": "(2022) 10 SCC 51", "relevance": "Comprehensive bail jurisprudence and personal liberty"}
        ],
        "timeline_estimate": "6-18 months depending on strategy and court workload",
        "confidence_score": 0.65
    }


# ==================== Counter Argument Generator ====================

class CounterArgumentRequest(BaseModel):
    """Request model for counter-argument generation"""
    legal_argument: str = Field(..., min_length=20, description="The legal argument to counter")
    case_type: str = Field(default="criminal", description="criminal, civil, constitutional, family, property")
    sections_involved: List[str] = Field(default_factory=list)
    client_role: str = Field(default="respondent", description="petitioner, respondent, accused, complainant")
    jurisdiction: str = Field(default="Delhi")
    focus_areas: List[str] = Field(default_factory=list, description="procedural, substantive, evidentiary, constitutional")


@app.post("/api/counter-arguments")
async def generate_counter_arguments(request: CounterArgumentRequest):
    """
    Counter Argument Generator — develop opposing viewpoints, rebuttals,
    procedural defenses, and relevant precedents.
    """
    try:
        import json as json_module

        # Step 1: Retrieve statutory context
        sections_query = " ".join(request.sections_involved[:5]) if request.sections_involved else ""
        search_query = f"{request.case_type} counter argument {sections_query} {request.legal_argument[:200]}"

        statutory_context = ""
        if vector_store and vector_store.statutory_index is not None:
            results = vector_store.hybrid_search_statutory(
                search_query, top_k=8, semantic_weight=0.6, bm25_weight=0.4
            )
            if results:
                statutory_context = "\n\n".join([
                    f"**{r.section_number}** ({r.law_type}): {r.text[:300]}"
                    for r in results[:6]
                ])

        focus_text = ", ".join(request.focus_areas) if request.focus_areas else "all applicable areas"

        # Step 2: Build prompt
        prompt = f"""You are an expert Indian legal strategist specializing in counter-arguments and rebuttals.

TASK: Analyze the following legal argument and generate comprehensive counter-arguments from the perspective of the {request.client_role}.

ORIGINAL ARGUMENT:
{request.legal_argument}

CONTEXT:
- Case Type: {request.case_type}
- Sections: {', '.join(request.sections_involved) if request.sections_involved else 'Not specified'}
- Jurisdiction: {request.jurisdiction}
- Client Role: {request.client_role}
- Focus Areas: {focus_text}

RELEVANT LEGAL PROVISIONS:
{statutory_context if statutory_context else 'Use general Indian legal knowledge.'}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "argument_analysis": {{
    "summary": "<1-2 sentence summary of the original argument>",
    "strengths": ["<strength1>", "<strength2>"],
    "weaknesses": ["<weakness1>", "<weakness2>", "<weakness3>"]
  }},
  "opposing_viewpoints": [
    {{
      "title": "<viewpoint title>",
      "argument": "<detailed opposing argument, 2-3 sentences>",
      "legal_basis": "<statutory or constitutional basis>",
      "strength": "strong/moderate/speculative"
    }}
  ],
  "rebuttals": [
    {{
      "original_point": "<point from the original argument being rebutted>",
      "counter": "<detailed rebuttal, 2-3 sentences>",
      "supporting_law": "<relevant section or principle>"
    }}
  ],
  "procedural_defenses": [
    {{
      "defense": "<procedural defense title>",
      "description": "<how to apply this defense>",
      "relevant_provision": "<applicable CrPC/CPC/Evidence Act section>",
      "effectiveness": "high/medium/low"
    }}
  ],
  "precedents": [
    {{
      "case_name": "<case name>",
      "citation": "<citation>",
      "ratio": "<ratio decidendi or key holding>",
      "application": "<how this precedent supports the counter-argument>"
    }}
  ],
  "recommended_strategy": "<2-3 sentence overall recommended approach>",
  "confidence_score": <0.0 to 1.0>
}}

Be thorough, cite real Indian legal provisions, and provide actionable counter-arguments.
"""

        # Step 3: Call LLM
        raw = await call_llm(prompt, temperature=0.4, max_tokens=3000)
        raw = raw.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json_module.loads(raw)
        return {"status": "success", "result": result, "grounded": bool(statutory_context)}

    except Exception as e:
        print(f"[CounterArgGen] Error: {e}")
        return {
            "status": "demo",
            "result": _get_demo_counter_arguments(request),
            "grounded": False,
            "note": "Demo response — AI service temporarily unavailable"
        }


def _get_demo_counter_arguments(req: CounterArgumentRequest) -> dict:
    sections = ', '.join(req.sections_involved) if req.sections_involved else 'General provisions'
    return {
        "argument_analysis": {
            "summary": f"The argument raises points under {sections} in a {req.case_type} matter. Analysis follows from the {req.client_role}'s perspective.",
            "strengths": [
                "Relies on established statutory framework",
                "Follows conventional legal reasoning"
            ],
            "weaknesses": [
                "Interpretation of key provisions may be contested",
                "Potential procedural irregularities not addressed",
                "Fails to account for recent judicial trends"
            ]
        },
        "opposing_viewpoints": [
            {
                "title": "Alternative Statutory Interpretation",
                "argument": "The cited provisions must be read harmoniously with other relevant sections. A purposive interpretation, as favoured by the Supreme Court, would yield a different conclusion that supports the respondent's position.",
                "legal_basis": "Section 6-8, General Clauses Act, 1897; Rule of harmonious construction",
                "strength": "strong"
            },
            {
                "title": "Constitutional Challenge",
                "argument": "The application of the cited provisions in the manner suggested violates fundamental rights guaranteed under Articles 14, 19, and 21 of the Constitution. Any interpretation must pass the test of reasonableness and proportionality.",
                "legal_basis": "Articles 14, 19, 21 — Constitution of India",
                "strength": "strong"
            },
            {
                "title": "Factual Dispute",
                "argument": "The factual foundation of the argument is contested. Material evidence suggests an alternative narrative that undermines the core premise of the original claim.",
                "legal_basis": "Sections 101-114, Indian Evidence Act (Bharatiya Sakshya Adhiniyam)",
                "strength": "moderate"
            }
        ],
        "rebuttals": [
            {
                "original_point": "Primary statutory interpretation",
                "counter": "The cited provision must be read in its entirety, including provisos and explanations. Selective reading distorts legislative intent. The Supreme Court has repeatedly held that statutes must be read as a whole.",
                "supporting_law": "Principles of statutory interpretation; CIT v. Hindustan Bulk Carriers (2003) 3 SCC 57"
            },
            {
                "original_point": "Reliance on factual assertions",
                "counter": "The burden of proof for the asserted facts lies with the proponent under Section 101 of the Evidence Act. The documentary evidence on record does not conclusively establish the claimed facts.",
                "supporting_law": "Section 101-103, Indian Evidence Act / BSA 2023"
            },
            {
                "original_point": "Applicability of cited precedent",
                "counter": "The cited precedent is distinguishable on facts. The ratio decidendi of the relied-upon judgment pertains to a materially different factual matrix and cannot be mechanically applied.",
                "supporting_law": "Doctrine of precedent; per incuriam rule"
            }
        ],
        "procedural_defenses": [
            {
                "defense": "Limitation / Delay",
                "description": "Challenge the timeliness of the action. If filing is beyond the prescribed limitation period, seek dismissal on this preliminary ground.",
                "relevant_provision": "Limitation Act, 1963; Section 3 — bar on suits beyond limitation",
                "effectiveness": "high"
            },
            {
                "defense": "Non-Joinder of Necessary Party",
                "description": "Argue that essential parties have not been impleaded, rendering the proceedings defective.",
                "relevant_provision": "Order 1 Rule 10, CPC / Section 43 BNSS",
                "effectiveness": "medium"
            },
            {
                "defense": "Lack of Territorial Jurisdiction",
                "description": "Challenge that the court lacks territorial or pecuniary jurisdiction over the subject matter.",
                "relevant_provision": "Section 15-20, CPC; Section 177-184 CrPC / BNSS",
                "effectiveness": "high"
            }
        ],
        "precedents": [
            {
                "case_name": "Lalita Kumari v. Govt. of U.P.",
                "citation": "(2014) 2 SCC 1",
                "ratio": "Mandatory FIR registration guidelines and scope of preliminary inquiry",
                "application": "Establishes procedural safeguards that may not have been followed"
            },
            {
                "case_name": "K.S. Puttaswamy v. Union of India",
                "citation": "(2017) 10 SCC 1",
                "ratio": "Right to privacy as a fundamental right under Article 21",
                "application": "Constitutional challenge to any overreach in the original argument"
            },
            {
                "case_name": "Mohd. Ahmed Khan v. Shah Bano Begum",
                "citation": "1985 AIR 945",
                "ratio": "Harmonious construction of personal law with constitutional provisions",
                "application": "Supports reading statutes consistently with constitutional values"
            }
        ],
        "recommended_strategy": f"Adopt a multi-pronged approach combining procedural challenges with substantive counter-arguments. Lead with the strongest procedural defense to seek early dismissal, while simultaneously preparing the substantive rebuttal for trial on merits.",
        "confidence_score": 0.72
    }


# ==================== Legal Sandbox ====================

class QuizRequest(BaseModel):
    topic: str = Field(..., description="e.g. Constitutional Law, IPC, CrPC, Evidence Act, Contract Law")
    difficulty: str = Field(default="medium", description="easy, medium, hard")
    num_questions: int = Field(default=5, ge=1, le=10)
    exam_type: str = Field(default="CLAT", description="CLAT, AILET, JUDICIARY, BAR")


class MootCourtRequest(BaseModel):
    case_scenario: str = Field(..., min_length=20)
    user_role: str = Field(default="petitioner", description="petitioner or respondent")
    user_argument: str = Field(..., min_length=10)
    court_level: str = Field(default="High Court")
    round_number: int = Field(default=1)
    history: List[dict] = Field(default_factory=list, description="Previous argument exchanges")


@app.post("/api/sandbox/quiz")
async def generate_quiz(request: QuizRequest):
    """Generate entrance exam MCQs for legal preparation."""
    try:
        import json as json_module

        prompt = f"""You are a legal exam expert for Indian law entrance exams.

Generate {request.num_questions} multiple-choice questions for {request.exam_type} exam preparation.

Topic: {request.topic}
Difficulty: {request.difficulty}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "questions": [
    {{
      "id": 1,
      "question": "<question text>",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "A",
      "explanation": "<detailed explanation with legal reasoning and any relevant section/case>",
      "difficulty": "{request.difficulty}",
      "topic_tag": "<sub-topic>"
    }}
  ]
}}

Make questions realistic for {request.exam_type}, test conceptual understanding, and provide thorough explanations citing Indian statutes and cases where relevant.
"""
        raw = await call_llm(prompt, temperature=0.6, max_tokens=3000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        result = json_module.loads(raw)
        return {"status": "success", "quiz": result}

    except Exception as e:
        print(f"[Sandbox Quiz] Error: {e}")
        return {"status": "demo", "quiz": _get_demo_quiz(request), "note": "Demo quiz — AI service unavailable"}


# --- DOCUMENT GENERATION ROUTES ---

class DocumentGenerationRequest(BaseModel):
    template_type: str
    form_data: Dict[str, Any]

@app.post("/api/documents/generate")
async def generate_legal_document(request: DocumentGenerationRequest):
    """
    Generate a professional legal document draft using AI & statutory context.
    """
    try:
        # 1. Search for statutory context related to the document type
        query = f"Statutory provisions and formal drafting structure for {request.template_type.replace('_', ' ')} in India"
        stat_results = vector_store.hybrid_search_statutory(query, top_k=5)
        
        # 2. Build generation prompt
        prompt = build_generation_prompt(request.template_type, request.form_data, stat_results)
        
        # 3. Call LLM
        answer = await call_llm(prompt, temperature=0.3, max_tokens=3000)
        answer = answer.strip()
        
        return {
            "status": "success",
            "document_draft": answer,
            "template": request.template_type,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[Document Gen] Error: {e}")
        # Fallback to a demo/structured draft if AI fails
        return {
            "status": "demo",
            "document_draft": f"IN THE COURT OF THE [DESIGNATION OF COURT] AT [LOCATION]\n\nCase No: [CASENO] of 2024\n\nIn the matter of: \n{request.form_data.get('petitioner_name', '[PETITIONER]')} ...Petitioner\n\nVERSUS\n\n{request.form_data.get('respondent_name', '[RESPONDENT]')} ...Respondent\n\nSubject: {request.template_type.replace('_', ' ').upper()} \n\nMOST RESPECTFULLY SHOWETH:\n\n1. That the petitioner is a law-abiding citizen of India.\n2. That the facts of the case are {request.form_data.get('facts', '[FACTS]')}.\n3. [ADDITIONAL GROUNDS BASED ON CONTEXT]\n\nPRAYER: Most respectfully prayed that this Hon'ble Court may be pleased to grant the relief as sought in the interest of justice.",
            "note": "Demo draft - server issue"
        }


def _get_demo_quiz(req: QuizRequest) -> dict:
    demos = {
        "Constitutional Law": [
            {"id": 1, "question": "Which Article of the Indian Constitution guarantees the Right to Equality?", "options": ["A) Article 12", "B) Article 14", "C) Article 19", "D) Article 21"], "correct_answer": "B", "explanation": "Article 14 guarantees equality before law and equal protection of laws. It embodies the concept of rule of law and prohibits class legislation while permitting reasonable classification.", "difficulty": req.difficulty, "topic_tag": "Fundamental Rights"},
            {"id": 2, "question": "The 'basic structure' doctrine was propounded in which landmark case?", "options": ["A) Golaknath v. State of Punjab", "B) Kesavananda Bharati v. State of Kerala", "C) Minerva Mills v. Union of India", "D) Maneka Gandhi v. Union of India"], "correct_answer": "B", "explanation": "In Kesavananda Bharati v. State of Kerala (1973), the Supreme Court held that Parliament's amending power under Article 368 does not extend to altering the basic structure of the Constitution.", "difficulty": req.difficulty, "topic_tag": "Constitutional Amendments"},
            {"id": 3, "question": "Which part of the Constitution deals with Directive Principles of State Policy?", "options": ["A) Part III", "B) Part IV", "C) Part IVA", "D) Part V"], "correct_answer": "B", "explanation": "Part IV (Articles 36-51) contains the Directive Principles of State Policy. Unlike Fundamental Rights (Part III), DPSPs are non-justiciable but fundamental in governance.", "difficulty": req.difficulty, "topic_tag": "DPSP"},
            {"id": 4, "question": "The concept of 'due process of law' was read into Article 21 in:", "options": ["A) A.K. Gopalan v. State of Madras", "B) Maneka Gandhi v. Union of India", "C) Olga Tellis v. Bombay Municipal Corporation", "D) Bachan Singh v. State of Punjab"], "correct_answer": "B", "explanation": "In Maneka Gandhi v. Union of India (1978), the Supreme Court expanded Article 21 by holding that 'procedure established by law' must be just, fair and reasonable — effectively reading in due process.", "difficulty": req.difficulty, "topic_tag": "Article 21"},
            {"id": 5, "question": "Residuary powers of legislation under the Indian Constitution belong to:", "options": ["A) State Legislature", "B) Concurrent List", "C) Parliament", "D) Local Bodies"], "correct_answer": "C", "explanation": "Under Article 248 read with Entry 97 of the Union List, residuary powers of legislation vest in Parliament. This is unlike the US Constitution where residuary powers lie with the states.", "difficulty": req.difficulty, "topic_tag": "Legislative Powers"},
        ],
        "IPC": [
            {"id": 1, "question": "Section 300 of IPC defines:", "options": ["A) Culpable Homicide", "B) Murder", "C) Attempt to Murder", "D) Grievous Hurt"], "correct_answer": "B", "explanation": "Section 300 IPC defines Murder. It specifies four clauses when culpable homicide amounts to murder. The distinction between murder (S.300) and culpable homicide not amounting to murder (S.299) is a key exam topic.", "difficulty": req.difficulty, "topic_tag": "Offences Against Body"},
            {"id": 2, "question": "Which section of IPC deals with the right of private defence?", "options": ["A) Section 96-106", "B) Section 76-85", "C) Section 107-120", "D) Section 34-38"], "correct_answer": "A", "explanation": "Sections 96-106 IPC cover the right of private defence of body and property. Section 96 states nothing is an offence done in exercise of private defence. Section 100 specifies when the right extends to causing death.", "difficulty": req.difficulty, "topic_tag": "General Exceptions"},
            {"id": 3, "question": "Criminal conspiracy is defined under which section?", "options": ["A) Section 107", "B) Section 120A", "C) Section 34", "D) Section 149"], "correct_answer": "B", "explanation": "Section 120A IPC defines criminal conspiracy as an agreement by two or more persons to do an illegal act or a legal act by illegal means. Section 120B prescribes the punishment.", "difficulty": req.difficulty, "topic_tag": "Criminal Conspiracy"},
            {"id": 4, "question": "The maxim 'actus non facit reum nisi mens sit rea' relates to:", "options": ["A) Strict liability", "B) Mens rea", "C) Res judicata", "D) Promissory estoppel"], "correct_answer": "B", "explanation": "This maxim means 'an act does not make a person guilty unless there is a guilty mind'. Mens rea is a fundamental principle of criminal law, embodied across IPC provisions.", "difficulty": req.difficulty, "topic_tag": "General Principles"},
            {"id": 5, "question": "Defamation under IPC is dealt with in:", "options": ["A) Section 499", "B) Section 503", "C) Section 415", "D) Section 463"], "correct_answer": "A", "explanation": "Section 499 IPC defines defamation — making or publishing an imputation concerning any person intending to harm, or knowing it would harm, that person's reputation. Section 500 prescribes punishment.", "difficulty": req.difficulty, "topic_tag": "Defamation"},
        ],
    }
    topic_questions = demos.get(req.topic, demos.get("Constitutional Law"))
    return {"questions": topic_questions[:req.num_questions]}


@app.post("/api/sandbox/moot-court")
async def moot_court_exchange(request: MootCourtRequest):
    """Moot Court simulator — AI plays opposing counsel and judge."""
    try:
        import json as json_module

        history_text = ""
        if request.history:
            for h in request.history[-4:]:
                history_text += f"\n[{h.get('role', 'unknown').upper()}]: {h.get('content', '')}\n"

        opposing = "respondent" if request.user_role == "petitioner" else "petitioner"

        prompt = f"""You are simulating an Indian {request.court_level} moot court proceeding.

CASE SCENARIO:
{request.case_scenario}

The student is arguing as the {request.user_role}. This is round {request.round_number}.

PREVIOUS EXCHANGES:
{history_text if history_text else "None — this is the opening round."}

STUDENT'S CURRENT ARGUMENT ({request.user_role.upper()}):
{request.user_argument}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "opposing_counsel": {{
    "argument": "<2-3 sentence counter-argument from {opposing}'s side>",
    "objections": ["<objection if any>"],
    "authorities_cited": ["<case or section cited>"]
  }},
  "judge_observations": {{
    "questions_to_student": ["<probing question 1>", "<probing question 2>"],
    "observations": "<1-2 sentence observation on the strength of arguments>",
    "ruling_hint": "<hint about which way the court is leaning>"
  }},
  "scoring": {{
    "argument_strength": <1-10>,
    "legal_reasoning": <1-10>,
    "citation_quality": <1-10>,
    "persuasiveness": <1-10>,
    "overall": <1-10>,
    "feedback": "<specific constructive feedback for the student>"
  }},
  "suggested_rebuttal_points": ["<point 1>", "<point 2>"]
}}

Be realistic, educational, and provide constructive feedback. Cite real Indian cases and statutes.
"""
        raw = await call_llm(prompt, temperature=0.5, max_tokens=2000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        result = json_module.loads(raw)
        return {"status": "success", "result": result}

    except Exception as e:
        print(f"[Moot Court] Error: {e}")
        return {
            "status": "demo",
            "result": _get_demo_moot_response(request),
            "note": "Demo response — AI service unavailable"
        }


def _get_demo_moot_response(req: MootCourtRequest) -> dict:
    opposing = "respondent" if req.user_role == "petitioner" else "petitioner"
    return {
        "opposing_counsel": {
            "argument": f"The learned {opposing} respectfully submits that the {req.user_role}'s argument, while creative, overlooks settled jurisprudence. The precedent cited is distinguishable on facts and the statutory interpretation urged is contrary to legislative intent.",
            "objections": ["The argument assumes facts not in evidence", "Misapplication of the cited precedent"],
            "authorities_cited": ["State of Maharashtra v. Indian Hotel & Restaurants (2013) 6 SCC 568", "Section 397 CrPC — Revisional jurisdiction"]
        },
        "judge_observations": {
            "questions_to_student": [
                "Counsel, how do you distinguish the Supreme Court's observation in the cited precedent from the facts of the present case?",
                "What is the specific statutory provision that confers jurisdiction on this court to grant the relief you seek?"
            ],
            "observations": "The court notes that both sides have raised interesting points of law. However, the petitioner's reliance on constitutional provisions requires stronger factual foundation.",
            "ruling_hint": "The court is inclined to examine the procedural aspects more closely before addressing the merits."
        },
        "scoring": {
            "argument_strength": 7,
            "legal_reasoning": 6,
            "citation_quality": 5,
            "persuasiveness": 7,
            "overall": 6,
            "feedback": "Good foundational argument but needs stronger citation support. Consider citing specific Supreme Court judgments and connecting the ratio decidendi directly to your factual matrix. Also address potential counter-arguments pre-emptively."
        },
        "suggested_rebuttal_points": [
            "Distinguish the opposing counsel's cited case on its specific factual matrix",
            "Invoke the constitutional angle under Article 21 to strengthen your position",
            "Address the procedural objection by citing the court's inherent powers under Section 482 CrPC"
        ]
    }


# ==================== Indian Kanoon API ====================



@app.get("/api/kanoon/search")
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


@app.get("/api/kanoon/doc/{doc_id}")
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


@app.get("/api/news")
async def get_legal_news(query: str = None):
    """
    Fetch recent legal news articles.
    """
    try:
        scraper = get_news_scraper()
        articles = await asyncio.to_thread(scraper.get_news, query)
        return {"status": "success", "articles": articles}
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return {"status": "error", "message": str(e), "articles": []}


# ==================== SSE Query Stream ====================

from fastapi.responses import StreamingResponse

@app.get("/api/query/stream")
async def query_stream(
    query: str,
    mode: str = "auto",
    session_id: str = None,
    custody_days: int = None,
    offense_sections: List[str] = None
):
    # Mock request object for the rest of the logic
    class MockRequest:
        pass
    request = MockRequest()
    request.query = query
    request.mode = mode
    request.session_id = session_id
    request.custody_days = custody_days
    request.offense_sections = offense_sections or []
    """
    Stream query processing events via SSE with FULL ENHANCED RAG.
    """
    from services.pipeline_events import SyncPipelineEmitter
    from reranker import SearchResult as RerankSearchResult
    import json
    import time as time_module
    
    async def event_generator():
        emitter = SyncPipelineEmitter()
        query_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        try:
            # Stage 1: Classification
            emitter.start('classify')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'classify', 'status': 'active'})}\n\n"
            
            classification = await query_classifier.classify(request.query)
            query_type = classification.query_type
            emitter.complete('classify', {'type': query_type.value})
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'classify', 'status': 'complete', 'data': {'type': query_type.value}})}\n\n"
            
            # Stage 2: Reformulation
            emitter.start('reformulate')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'reformulate', 'status': 'active'})}\n\n"
            
            reformulated = query_reformulator.reformulate(request.query)
            requested_sections = reformulated.extracted_sections if hasattr(reformulated, 'extracted_sections') else []
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'reformulate', 'status': 'complete', 'data': {'sections': len(requested_sections)}})}\n\n"
            
            # Stage 2.5: Session Documents (parallel to statutory retrieval)
            session_documents = []
            if request.session_id:
                session = session_manager.get_session(request.session_id)
                if session and session.documents:
                    doc_search_results = session.search(reformulated.enhanced_query, top_k=5)
                    session_documents = [
                        {"filename": r.filename, "text": r.text, "document_type": r.document_type, "is_statutory": False, "score": r.score}
                        for r in doc_search_results
                    ]
            
            # Stage 3: Retrieval
            emitter.start('retrieve')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'retrieve', 'status': 'active'})}\n\n"
            
            # Run statutory and case law retrieval in parallel
            async def get_statutory():
                return vector_store.hybrid_search_statutory(
                    reformulated.enhanced_query, top_k=TOP_K_STATUTORY * 3,
                    semantic_weight=0.6, bm25_weight=0.4
                ) if vector_store and vector_store.statutory_index else []
            
            async def get_case_law():
                if query_type == QueryType.BAIL_QUERY and vector_store and vector_store.case_law_index:
                    return vector_store.search_case_law(reformulated.enhanced_query, top_k=TOP_K_CASE_LAW * 2)
                return []
            
            initial_statutory, initial_case_law = await asyncio.gather(get_statutory(), get_case_law())
            
            total_retrieved = len(initial_statutory) + len(initial_case_law)
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'retrieve', 'status': 'complete', 'data': {'results': total_retrieved}})}\n\n"
            
            # Stage 4: Reranking
            emitter.start('rerank')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'rerank', 'status': 'active'})}\n\n"
            
            statutory_results = []
            if initial_statutory:
                rerank_inputs = [RerankSearchResult(chunk_id=r.chunk_id, text=r.text, score=r.score, law_type=r.law_type, section_number=r.section_number, source_dataset=r.source_dataset, dataset_type=r.dataset_type, metadata=r.metadata) for r in initial_statutory]
                statutory_results = reranker.rerank(results=rerank_inputs, requested_sections=requested_sections, top_k=TOP_K_STATUTORY, mode='precision' if requested_sections else 'balanced')
            
            bail_results = []
            if initial_case_law:
                rerank_case_law = [RerankSearchResult(chunk_id=r.chunk_id, text=r.text, score=r.score, law_type=r.law_type, section_number=r.section_number, source_dataset=r.source_dataset, dataset_type=r.dataset_type, metadata=r.metadata) for r in initial_case_law]
                bail_results = reranker.rerank(results=rerank_case_law, requested_sections=[], top_k=TOP_K_CASE_LAW, mode='recall')
            
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'rerank', 'status': 'complete'})}\n\n"
            
            # Stage 5: Scoring
            emitter.start('score')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'score', 'status': 'active'})}\n\n"
            
            retrieval_confidence = confidence_scorer.compute_confidence(query=request.query, reformulated_query=reformulated, results=statutory_results, query_type=query_type.value)
            from config import ConfidenceLevel, FALLBACK_LABELS
            confidence_level, confidence_reason = confidence_scorer.get_response_mode(retrieval_confidence)
            
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'score', 'status': 'complete', 'data': {'confidence': round(retrieval_confidence.overall_score, 2), 'level': confidence_level.value}})}\n\n"
            
            # Stage 6: Generation
            emitter.start('generate')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'generate', 'status': 'active'})}\n\n"
            
            if confidence_level == ConfidenceLevel.HIGH: grounding_status = "pass"; use_fallback = False
            elif confidence_level == ConfidenceLevel.MEDIUM: grounding_status = "partial"; use_fallback = False
            else: grounding_status = "fail"; use_fallback = True
            
            bail_assessment = None
            if query_type == QueryType.BAIL_QUERY:
                stat_ctx = [{"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "source": r.source_dataset} for r in statutory_results]
                bail_ctx = [{"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "metadata": r.metadata} for r in bail_results]
                if session_documents:
                    prompt = build_prompt_with_documents(query=request.query, statutory_context=stat_ctx, document_context=session_documents, bail_context=bail_ctx, is_bail_query=True)
                    answer = await call_llm(prompt)
                    bail_assessment = {"bail_likelihood": "Document Analysis", "legal_reasoning": {"bailable_status": "See document", "max_punishment": "See document", "severity_score": 0, "applicable_crpc": ["Based on uploaded document"]}, "explanation": "Analysis based on uploaded court document/FIR."}
                    confidence_score = 0.85
                else:
                    evaluation = await bail_evaluator.evaluate(query=request.query, statutory_context=stat_ctx, bail_precedents=bail_ctx, custody_duration_days=request.custody_days, offence_sections=request.offense_sections)
                    answer = evaluation.explanation; bail_assessment = evaluation.to_dict(); confidence_score = evaluation.confidence_score
            else:
                structured_context_text = context_builder.build_structured_context(
                    statutory_results=statutory_results,
                    case_law_results=bail_results if bail_results else None,
                    uploaded_docs=session_documents,
                    max_tokens=3000
                )
                prompt = f"You are JustiAssist, an AI legal assistant for Indian criminal law.\n\nANSWER MODE: {grounding_status}\n\nUSER QUERY: {request.query}\n\nRETRIEVED LEGAL CONTEXT:\n{structured_context_text}\n\n"
                if use_fallback: prompt += f"FALLBACK MODE — The retrieved context is limited.\nReason: {confidence_reason}\n\nProvide the best answer using general legal knowledge. Cite section numbers if possible. Do NOT add disclaimers."
                else: prompt += "GROUNDED MODE (High Retrieval Confidence)\nAnswer ONLY from the retrieved context above. Cite exact section numbers. Do NOT assume provisions not in context."
                answer = await call_llm(prompt, temperature=0.3, max_tokens=2000)
                confidence_score = 0.75 + (retrieval_confidence.overall_score * 0.2) if not use_fallback else 0.4

            from citation_validator import citation_validator
            all_ctx_flat = [{"section_number": r.section_number, "law_type": r.law_type, "text": r.text} for r in (statutory_results + bail_results)]
            cit_val = citation_validator.validate(response=answer, context_chunks=all_ctx_flat, strict=False)
            if not cit_val.is_valid:
                answer = citation_validator.sanitize_response(answer, cit_val)
                confidence_score = max(confidence_score - 0.15, 0.3)
            grounding_eval = feedback_evaluator.evaluate(answer, all_ctx_flat, request.query)
            if grounding_eval.grounding_score > 0.7: confidence_score = min(confidence_score + 0.1, 0.95)
            
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'generate', 'status': 'complete'})}\n\n"
            
            # Extra enrichment
            from services.indian_kanoon import get_kanoon_api
            kanoon_query = " ".join(requested_sections[:2]) + " bail judgment" if requested_sections else request.query[:50]
            async def fetch_kanoon():
                try:
                    api = get_kanoon_api()
                    if api.api_key:
                        res = await asyncio.wait_for(api.search(kanoon_query, doc_type="judgments"), timeout=3.0)
                        return [{"title": d.title, "citation": d.citation, "court": d.court, "date": d.date, "url": d.url, "preview": (d.headline or "")[:150]} for d in res.documents[:3]]
                except: pass
                return []
            async def fetch_news():
                try:
                    scraper = get_news_scraper()
                    news_q = " ".join(requested_sections[:2]) + " India law" if requested_sections else "Indian law " + request.query[:30]
                    articles = await asyncio.to_thread(scraper.get_news, news_q)
                    return [{"title": a.get("title", ""), "source": a.get("source", "Unknown"), "date": a.get("published date", ""), "url": a.get("url", "")} for a in articles[:2]]
                except: pass
                return []
            kanoon_cases, news_context = await asyncio.gather(fetch_kanoon(), fetch_news())
            
            emitter.complete('generate')
            
            response_data = {
                "query": request.query, "query_type": query_type.value, "answer": answer, "citations": [c.model_dump() for c in format_citations(statutory_results + bail_results)],
                "confidence_score": round(confidence_score, 2), "bail_assessment": bail_assessment, "grounding_status": grounding_status,
                "processing_info": emitter.get_summary(), "kanoon_cases": kanoon_cases, "news_context": news_context,
                "sources_used": ["local_vectors"] + (["indian_kanoon"] if kanoon_cases else []) + (["legal_news"] if news_context else [])
            }
            yield f"data: {json.dumps({'type': 'complete', 'data': {'response': response_data}})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )



# ==================== Document Upload ====================

def extract_text_from_file(file_path: Path, filename: str) -> str:
    """Extract text from uploaded file"""
    content = ""
    
    if filename.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    elif filename.endswith('.pdf'):
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    content += page.extract_text() + "\n"
        except ImportError:
            # Fallback if PyPDF2 not installed
            content = "[PDF extraction requires PyPDF2. Install with: pip install PyPDF2]"
        except Exception as e:
            content = f"[Error extracting PDF: {str(e)}]"
    elif filename.endswith('.docx'):
        try:
            from docx import Document
            doc = Document(str(file_path))
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            content = "\n".join(paragraphs)
        except ImportError:
            content = "[DOCX extraction requires python-docx. Install with: pip install python-docx]"
        except Exception as e:
            content = f"[Error extracting DOCX: {str(e)}]"
    else:
        # Try reading as text
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except:
            content = "[Unable to extract text from this file format]"
    
    return content


@app.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    query: str = Form(...),
    mode: str = Form(default="auto"),
    session_id: str = Form(default=None),
    document_type: str = Form(default="OTHER")
):
    """
    Upload a document (FIR, charge sheet, case summary) for case-specific analysis.
    
    Documents are:
    - Parsed and chunked
    - Indexed in session-level vector store
    - Clearly marked as NON-STATUTORY evidence
    
    Documents may be used for:
    - Fact extraction
    - Case-specific reasoning
    - Bail evaluation context
    
    Documents will NEVER:
    - Override statutory law
    - Be treated as authoritative legislation
    """
    # Validate file
    allowed_extensions = ['.txt', '.pdf', '.doc', '.docx']
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Size limit (5MB)
    max_size = 5 * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum 5MB allowed.")
    
    # Save temporarily and extract text
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)
    
    try:
        document_text = extract_text_from_file(tmp_path, file.filename)
    finally:
        tmp_path.unlink()  # Clean up temp file
    
    if not document_text or len(document_text) < 10:
        raise HTTPException(status_code=400, detail="Could not extract text from document.")
    
    # Get or create session
    session = session_manager.get_or_create_session(session_id)
    
    # Add document to session (chunked and indexed)
    uploaded_doc = session.add_document(
        filename=file.filename,
        text=document_text,
        document_type=document_type
    )
    
    processing_info = {
        "steps": [
            f"Uploaded document: {file.filename}",
            f"Document type: {document_type} (NON-STATUTORY)",
            f"Created {len(uploaded_doc.chunks)} chunks",
            f"Session ID: {session.session_id}"
        ]
    }
    
    # Classify query
    if mode == "auto":
        classification = await query_classifier.classify(query)
        query_type = classification.query_type
    elif mode == "bail":
        query_type = QueryType.BAIL_QUERY
    else:
        query_type = QueryType.LEGAL_INFO
    
    processing_info["steps"].append(f"Query type: {query_type.value}")
    
    # Reformulate query
    reformulated = query_reformulator.reformulate(query)
    
    # Search session documents (NON-STATUTORY)
    doc_results = session.search(reformulated.enhanced_query, top_k=3)
    processing_info["steps"].append(f"Retrieved {len(doc_results)} chunks from uploaded documents")
    
    # Search statutory index (AUTHORITATIVE)
    statutory_results = vector_store.search_statutory(
        reformulated.enhanced_query,
        top_k=TOP_K_STATUTORY
    ) if vector_store and vector_store.statutory_index else []
    processing_info["steps"].append(f"Retrieved {len(statutory_results)} statutory provisions")
    
    bail_results = []
    if query_type == QueryType.BAIL_QUERY and vector_store and vector_store.bail_index:
        bail_results = vector_store.search_bail(
            reformulated.enhanced_query,
            top_k=TOP_K_BAIL
        )
        processing_info["steps"].append(f"Retrieved {len(bail_results)} bail precedents")
    
    # Format contexts
    statutory_context = [
        {
            "section_number": r.section_number,
            "law_type": r.law_type,
            "text": r.text,
            "source": r.source_dataset,
            "is_statutory": True,
            "is_authoritative": True
        }
        for r in statutory_results
    ]
    
    # Format document context with NON-STATUTORY markers
    document_context = [
        {
            "filename": r.filename,
            "text": r.text,
            "document_type": r.document_type,
            "is_statutory": False,  # EXPLICIT
            "is_authoritative": False,  # EXPLICIT
            "citation_prefix": r.citation_prefix
        }
        for r in doc_results
    ]
    
    bail_context = [
        {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "metadata": r.metadata}
        for r in bail_results
    ]
    
    # Build prompt with proper document handling
    if query_type == QueryType.BAIL_QUERY:
        # If document is uploaded, use enhanced document-aware prompt instead of rule-based evaluator
        if document_context:
            # Build enhanced prompt that prioritizes document analysis
            prompt = build_prompt_with_documents(
                query=query,
                statutory_context=statutory_context,
                document_context=document_context,
                bail_context=bail_context,
                is_bail_query=True
            )
            
            answer = await call_llm(prompt)
            confidence_score = 0.85  # High confidence when document is available
            
            # Create assessment from document analysis
            bail_assessment = {
                "likelihood": "See Document Analysis Above",
                "status": "Document-Based Analysis",
                "max_punishment": "See document sections",
                "severity_score": 0,
                "applicable_provisions": ["Based on uploaded document"],
                "explanation": "Analysis based on uploaded court document/FIR."
            }
        else:
            # No documents - use rule-based evaluator
            combined_context = statutory_context
            
            evaluation = await bail_evaluator.evaluate(
                query=query,
                statutory_context=combined_context,
                bail_precedents=bail_context,
                custody_duration_days=None,
                offence_sections=None
            )
            
            answer = evaluation.explanation
            confidence_score = evaluation.confidence_score
            bail_assessment = evaluation.to_dict()
    else:
        # Build prompt with document constraints
        prompt = build_prompt_with_documents(
            query=query,
            statutory_context=statutory_context,
            document_context=document_context,
            bail_context=bail_context,
            is_bail_query=False
        )
        
        answer = await call_llm(prompt)
        confidence_score = 0.7
        bail_assessment = None
    
    processing_info["steps"].append("Generated response with document + statutory context")
    
    # Grounding evaluation (checks both sources)
    all_context = statutory_context + [{"text": d["text"]} for d in document_context]
    grounding_eval = feedback_evaluator.evaluate(answer, all_context, query)
    
    # Format citations - STATUTORY first (authoritative), then documents
    citations = []
    
    # Statutory citations (authoritative)
    for r in statutory_results:
        citations.append({
            "section": r.section_number,
            "law_type": r.law_type,
            "text_preview": r.text[:200] + "..." if len(r.text) > 200 else r.text,
            "source": r.source_dataset,
            "relevance_score": round(r.score, 3),
            "is_authoritative": True,
            "is_statutory": True
        })
    
    # Document citations (non-statutory evidence)
    for r in doc_results:
        citations.append(format_document_citation(
            filename=r.filename,
            text_preview=r.text,
            relevance_score=r.score
        ))
    
    return {
        "query": query,
        "session_id": session.session_id,
        "document_name": file.filename,
        "document_type": document_type,
        "document_chunks": len(uploaded_doc.chunks),
        "document_preview": document_text[:500] + "..." if len(document_text) > 500 else document_text,
        "query_type": query_type.value,
        "answer": answer,
        "citations": citations,
        "confidence_score": round(confidence_score, 2),
        "bail_assessment": bail_assessment,
        "grounding_status": grounding_eval.status.value,
        "processing_info": processing_info,
        "document_notice": "⚠️ Uploaded documents are treated as case evidence, NOT statutory law. Citations clearly distinguish between authoritative legal provisions and user-uploaded evidence."
    }


@app.get("/session/{session_id}/documents")
async def list_session_documents(session_id: str):
    """List all documents in a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    return {
        "session_id": session_id,
        "documents": session.list_documents(),
        "total_chunks": len(session.chunk_metadata)
    }


@app.delete("/session/{session_id}/documents")
async def clear_session_documents(session_id: str):
    """Clear all documents from a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    doc_count = len(session.documents)
    session.clear()
    
    return {
        "session_id": session_id,
        "message": f"Cleared {doc_count} document(s) from session",
        "documents_cleared": doc_count
    }


@app.delete("/session/{session_id}/document/{document_id}")
async def delete_document(session_id: str, document_id: str):
    """Delete a specific document from session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    if document_id not in session.documents:
        raise HTTPException(status_code=404, detail="Document not found in session")
    
    # Remove document and rebuild index
    del session.documents[document_id]
    
    # Rebuild index without deleted document chunks
    session.chunk_metadata = [c for c in session.chunk_metadata if c['document_id'] != document_id]
    
    # Rebuild FAISS index
    if session.chunk_metadata:
        session.index = None  # Reset
        texts = [c['text'] for c in session.chunk_metadata]
        model = session._get_embedding_model()
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        import faiss
        session.index = faiss.IndexFlatIP(session._embedding_dim)
        session.index.add(embeddings)
    else:
        session.index = None
    
    return {
        "session_id": session_id,
        "document_id": document_id,
        "message": "Document deleted successfully",
        "remaining_documents": len(session.documents)
    }


@app.post("/session/{session_id}/query")
async def query_with_session(
    session_id: str,
    request: QueryRequest
):
    """
    Query using existing session documents.
    Documents from previous uploads in this session are automatically included.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    query = request.query.strip()
    
    # Classify and reformulate
    if request.mode == "auto":
        classification = await query_classifier.classify(query)
        query_type = classification.query_type
    elif request.mode == "bail":
        query_type = QueryType.BAIL_QUERY
    else:
        query_type = QueryType.LEGAL_INFO
    
    reformulated = query_reformulator.reformulate(query)
    
    # Search session documents
    doc_results = session.search(reformulated.enhanced_query, top_k=3)
    
    # Search statutory
    statutory_results = vector_store.hybrid_search_statutory(
        reformulated.enhanced_query,
        top_k=TOP_K_STATUTORY
    ) if vector_store and vector_store.statutory_index else []
    
    bail_results = []
    if query_type == QueryType.BAIL_QUERY and vector_store and vector_store.bail_index:
        bail_results = vector_store.search_bail(
            reformulated.enhanced_query,
            top_k=TOP_K_BAIL
        )
    
    # Format contexts
    statutory_context = [
        {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "source": r.source_dataset}
        for r in statutory_results
    ]
    
    document_context = [
        {"filename": r.filename, "text": r.text, "document_type": r.document_type}
        for r in doc_results
    ]
    
    # Generate response
    prompt = build_prompt_with_documents(
        query=query,
        statutory_context=statutory_context,
        document_context=document_context,
        bail_context=[{"text": r.text} for r in bail_results] if bail_results else None,
        is_bail_query=(query_type == QueryType.BAIL_QUERY)
    )
    
    answer = await call_llm(prompt)
    
    # Format citations
    citations = []
    for r in statutory_results:
        citations.append({
            "section": r.section_number,
            "law_type": r.law_type,
            "text_preview": r.text[:200] + "...",
            "is_authoritative": True
        })
    for r in doc_results:
        citations.append(format_document_citation(r.filename, r.text, r.score))
    
    return {
        "query": query,
        "session_id": session_id,
        "documents_searched": len(session.documents),
        "query_type": query_type.value,
        "answer": answer,
        "citations": citations,
        "confidence_score": 0.75
    }


# ==================== Main ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
