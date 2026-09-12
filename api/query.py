
from audit_logger import audit_logger
from metrics import metrics
from config import GROQ_MODEL
from llm_provider import LLMProvider


import asyncio
from datetime import datetime
from document_session import session_manager
from config import TOP_K_STATUTORY, TOP_K_CASE_LAW, AnswerMode, DEFAULT_ANSWER_MODE, RETRIEVAL_CONFIDENCE_THRESHOLD, INSUFFICIENT_CONTEXT_RESPONSE
from agents.query_classifier import QueryType
from prompts.templates import build_prompt_with_documents, build_legal_prompt, build_bail_prompt, format_document_citation
from llm_provider import call_llm
from services.news_scraper import get_news_scraper

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
import uuid
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from core.dependencies import deps
from services.auth import get_current_user_optional
from services.chat_memory import save_message, format_history_for_context

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

router = APIRouter()

@router.post("/api/v2/query")
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
    if deps.vector_store is None or deps.vector_store.statutory_index is None:
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
    result = await deps.crew_orchestrator.process_query(
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


@router.get("/api/v2/query/stream")
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
            result = await deps.crew_orchestrator.process_query(
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


@router.post("/query", response_model=QueryResponse)
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
    
    if deps.vector_store is None or deps.vector_store.statutory_index is None:
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
        classification = await deps.query_classifier.classify(query)
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
    reformulated = deps.query_reformulator.reformulate(query)
    requested_sections = reformulated.extracted_sections
    processing_info["steps"].append(
        f"✓ Query enhanced: {len(reformulated.search_terms)} terms, "
        f"{len(requested_sections)} sections detected"
    )
    print(f"[ENHANCED REFORMULATION] Sections: {requested_sections}")
    print(f"[ENHANCED REFORMULATION] Enhanced query: {reformulated.enhanced_query}")
    
    # Step 3: RETRIEVAL PIPELINE
    if deps.retrieval_pipeline:
        evidence = deps.retrieval_pipeline.run(
            query=query,
            enhanced_query=reformulated.enhanced_query,
            query_type=query_type,
            extracted_sections=requested_sections,
            extracted_law_types=reformulated.extracted_law_types,
            session_id=request.session_id
        )
        session_documents = evidence.session_documents
        statutory_results = evidence.statutory_results
        bail_results = evidence.case_law_results
        
        if session_documents:
            processing_info["steps"].append(f"✓ Retrieved {len(session_documents)} chunks from uploaded documents")
            print(f"[SESSION DOCS] Found {len(session_documents)} document chunks for session {request.session_id}")
            
        if statutory_results:
            processing_info["steps"].append(f"✓ Retrieved and reranked {len(statutory_results)} top statutory results")
        else:
            processing_info["steps"].append("⚠ No statutory results found")
            
        if bail_results:
            processing_info["steps"].append(f"✓ Retrieved {len(bail_results)} case law precedents")
    else:
        session_documents = []
        statutory_results = []
        bail_results = []
        processing_info["steps"].append("⚠ Retrieval pipeline not initialized")
    
    # Step 4: STRUCTURED CONTEXT BUILDING
    structured_context_text = deps.context_builder.build_structured_context(
        statutory_results=statutory_results,
        case_law_results=bail_results if bail_results else None,
        uploaded_docs=session_documents if 'session_documents' in locals() else None,
        max_tokens=3000
    )
    
    processing_info["steps"].append("✓ Built structured, evidence-aware context")
    
    # Step 5: MULTI-FACTOR CONFIDENCE SCORING
    retrieval_confidence = deps.confidence_scorer.compute_confidence(
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
    
    confidence_level, confidence_reason = deps.confidence_scorer.get_response_mode(retrieval_confidence)
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
            evaluation = await deps.bail_evaluator.evaluate(
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
    grounding_eval = deps.feedback_evaluator.evaluate(answer, all_context, query)
    
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


@router.get("/api/query/stream")
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
            
            classification = await deps.query_classifier.classify(request.query)
            query_type = classification.query_type
            emitter.complete('classify', {'type': query_type.value})
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'classify', 'status': 'complete', 'data': {'type': query_type.value}})}\n\n"
            
            # Stage 2: Reformulation
            emitter.start('reformulate')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'reformulate', 'status': 'active'})}\n\n"
            
            reformulated = deps.query_reformulator.reformulate(request.query)
            requested_sections = reformulated.extracted_sections if hasattr(reformulated, 'extracted_sections') else []
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'reformulate', 'status': 'complete', 'data': {'sections': len(requested_sections)}})}\n\n"
            
            # Run Retrieval Pipeline
            if deps.retrieval_pipeline:
                evidence = deps.retrieval_pipeline.run(
                    query=request.query,
                    enhanced_query=reformulated.enhanced_query,
                    query_type=query_type,
                    extracted_sections=requested_sections,
                    extracted_law_types=reformulated.extracted_law_types,
                    session_id=request.session_id
                )
                session_documents = evidence.session_documents
                statutory_results = evidence.statutory_results
                bail_results = evidence.case_law_results
            else:
                session_documents, statutory_results, bail_results = [], [], []
                
            total_retrieved = len(statutory_results) + len(bail_results)
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'retrieve', 'status': 'complete', 'data': {'results': total_retrieved}})}\n\n"
            
            # Stage 4: Reranking (Already done inside pipeline, just emit complete)
            emitter.start('rerank')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'rerank', 'status': 'active'})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'rerank', 'status': 'complete'})}\n\n"
            
            # Stage 5: Scoring
            emitter.start('score')
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'score', 'status': 'active'})}\n\n"
            
            retrieval_confidence = deps.confidence_scorer.compute_confidence(query=request.query, reformulated_query=reformulated, results=statutory_results, query_type=query_type.value)
            from config import ConfidenceLevel, FALLBACK_LABELS
            confidence_level, confidence_reason = deps.confidence_scorer.get_response_mode(retrieval_confidence)
            
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
                    evaluation = await deps.bail_evaluator.evaluate(query=request.query, statutory_context=stat_ctx, bail_precedents=bail_ctx, custody_duration_days=request.custody_days, offence_sections=request.offense_sections)
                    answer = evaluation.explanation; bail_assessment = evaluation.to_dict(); confidence_score = evaluation.confidence_score
            else:
                structured_context_text = deps.context_builder.build_structured_context(
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
            grounding_eval = deps.feedback_evaluator.evaluate(answer, all_ctx_flat, request.query)
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



