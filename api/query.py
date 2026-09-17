import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.dependencies import deps
from services.auth import get_current_user_optional, decode_token, decode_sse_ticket
from services.database import get_db_session, User
from services.chat_memory import save_message, format_history_for_context
import logging

logger = logging.getLogger(__name__)

from agents.state import AgentState

# ==================== Models ====================
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    mode: Optional[str] = Field(default="auto", description="auto, legal, or bail")
    custody_days: Optional[int] = Field(default=None, ge=0)
    offense_sections: Optional[List[str]] = Field(default=None)
    session_id: Optional[str] = Field(default=None, description="Session ID for uploaded documents")
    conversation_id: Optional[str] = Field(default=None, description="ID for persistent chat thread")

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

class VerificationSummary(BaseModel):
    claim_id: str
    verdict: str
    evidence_ids: List[str]

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
    is_abstention: bool = False
    verification_verdicts: List[VerificationSummary] = Field(default_factory=list)

router = APIRouter()

def _state_to_response(state: AgentState) -> QueryResponse:
    qtype_val = state.query_type.value if hasattr(state.query_type, 'value') else state.query_type
    
    verifications = []
    if getattr(state, "generated_response", None) and getattr(state.generated_response, "verifications", None):
        for v in state.generated_response.verifications:
            verdict_str = v.verdict.value if hasattr(v.verdict, 'value') else str(v.verdict)
            verifications.append(VerificationSummary(
                claim_id=v.claim_id,
                verdict=verdict_str,
                evidence_ids=v.evidence_ids
            ))
            
    return QueryResponse(
        query=state.query,
        query_type=qtype_val,
        answer=state.final_answer or "",
        citations=[Citation(**c) for c in state.citations],
        confidence_score=state.confidence_score,
        bail_assessment=state.bail_assessment,
        grounding_status=state.grounding_status,
        processing_info=state.processing_info,
        kanoon_cases=[KanoonCaseResponse(**k) for k in state.kanoon_cases],
        news_context=[NewsContextResponse(**n) for n in state.news_context],
        sources_used=state.sources_used,
        fetch_times_ms={},
        is_abstention=state.is_abstention,
        verification_verdicts=verifications
    )

@router.post("/query", response_model=QueryResponse)
@router.post("/api/v2/query", response_model=QueryResponse)
async def process_query_endpoint(
    request: QueryRequest,
    user = Depends(get_current_user_optional)
):
    """
    Canonical query processing endpoint.
    Uses unified AgentOrchestrator to prevent pipeline duplication.
    """
    if deps.agent_orchestrator is None:
        raise HTTPException(status_code=503, detail="Agent Orchestrator not initialized.")

    query = request.query.strip()
    conversation_id = request.conversation_id or str(uuid.uuid4())[:12]
    
    chat_context = ""
    if user:
        chat_context = await format_history_for_context(
            user_id=user.id,
            conversation_id=conversation_id,
            max_messages=6,
            max_chars=2000
        )
        from core.exceptions import ConversationOwnershipError
        try:
            await save_message(
                user_id=user.id, role="user", content=query,
                conversation_id=conversation_id, session_id=request.session_id
            )
        except ConversationOwnershipError as e:
            raise HTTPException(status_code=403, detail=str(e))

    state = AgentState(
        query=query,
        mode=request.mode,
        chat_history=chat_context,
        session_documents=[], # Could fetch from session_manager if needed
        custody_days=request.custody_days,
        offense_sections=request.offense_sections or [],
        session_id=request.session_id
    )

    state = await deps.agent_orchestrator.run(state)

    if user:
        qtype_val = state.query_type.value if hasattr(state.query_type, 'value') else state.query_type
        await save_message(
            user_id=user.id, role="assistant", content=state.final_answer,
            conversation_id=conversation_id, query_type=qtype_val,
            confidence_score=state.confidence_score,
            grounding_status=state.grounding_status,
            agents_used=state.agents_used, sources_used=state.sources_used,
            session_id=request.session_id
        )

    return _state_to_response(state)

@router.get("/api/query/stream")
@router.get("/api/v2/query/stream")
async def query_stream_endpoint(
    query: str,
    mode: str = "auto",
    session_id: str = None,
    conversation_id: str = None,
    custody_days: int = None,
    offense_sections: List[str] = None,
    ticket: str = None
):
    """
    Canonical SSE stream endpoint.
    Emits events while routing through the same AgentOrchestrator.
    """
    if not ticket:
        raise HTTPException(status_code=401, detail="Missing SSE ticket")
        
    user = decode_sse_ticket(ticket)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired SSE ticket")
            
    async def event_generator():
        try:
            conv_id = conversation_id or str(uuid.uuid4())[:12]
            chat_context = ""
            if user:
                chat_context = await format_history_for_context(user_id=user.id, conversation_id=conv_id)
                from core.exceptions import ConversationOwnershipError
                try:
                    await save_message(user_id=user.id, role="user", content=query, conversation_id=conv_id, session_id=session_id)
                except ConversationOwnershipError as e:
                    logger.error(f"Conversation ownership error in SSE: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'message': 'An internal error occurred while processing your request.'})}\n\n"
                    return
                
            state = AgentState(
                query=query.strip(),
                mode=mode,
                chat_history=chat_context,
                custody_days=custody_days,
                offense_sections=offense_sections or [],
                session_id=session_id
            )
            
            # SSE emitter callback
            stage_events = []
            def on_stage(stage: str, status: str, data: Any = None):
                stage_events.append({"stage": stage, "status": status, "data": data})
                
            # Actually we can yield directly if we pass an async callback,
            # but AgentOrchestrator.run is fully async and the callback is sync.
            # To yield as it happens, we can use an asyncio.Queue, OR
            # we can run the orchestrator in a background task and yield from the queue.
            
            queue = asyncio.Queue()
            def sync_emit(stage: str, status: str, data: Any = None):
                queue.put_nowait({"type": "stage", "stage": stage, "status": status, "data": data})
                
            async def run_orchestrator():
                try:
                    res_state = await deps.agent_orchestrator.run(state, on_stage=sync_emit)
                    queue.put_nowait({"type": "complete", "state": res_state})
                except Exception as e:
                    logger.error(f"Error in orchestrator during SSE: {e}", exc_info=True)
                    queue.put_nowait({"type": "error", "message": "An internal error occurred while processing your request."})

            task = asyncio.create_task(run_orchestrator())
            
            while True:
                msg = await queue.get()
                if msg["type"] == "complete":
                    final_state = msg["state"]
                    if user:
                        qtype_val = final_state.query_type.value if hasattr(final_state.query_type, 'value') else final_state.query_type
                        await save_message(
                            user_id=user.id, role="assistant", content=final_state.final_answer,
                            conversation_id=conv_id, query_type=qtype_val,
                            confidence_score=final_state.confidence_score, grounding_status=final_state.grounding_status,
                            agents_used=final_state.agents_used, sources_used=final_state.sources_used,
                            session_id=session_id
                        )
                    resp = _state_to_response(final_state).model_dump()
                    yield f"data: {json.dumps({'type': 'complete', 'data': {'response': resp}})}\n\n"
                    break
                elif msg["type"] == "error":
                    # Generic message already formatted or we can format it here.
                    # Since queue.put_nowait adds it, we should sanitize it. Wait, the inner error was added to queue.
                    # Let's sanitize everything just in case.
                    yield f"data: {json.dumps({'type': 'error', 'message': 'An internal error occurred while processing your request.'})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps(msg)}\n\n"
                    
        except Exception as e:
            logger.error(f"Unhandled SSE stream exception: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'An internal error occurred while processing your request.'})}\n\n"
            
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
