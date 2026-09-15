import time
import logging
from typing import Dict, Any, Optional, Callable
from agents.state import AgentState
from agents.router_agent import RouterAgent
from agents.research_agent import ResearchAgent
from agents.analysis_agent import AnalysisAgent
from agents.response_agent import ResponseAgent
from agents.verification_agent import VerificationAgent

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Unified native agent orchestrator replacing JustiAssistCrew.
    Coordinates execution of agents in a strict pipeline.
    """
    def __init__(self, vector_store=None, reranker=None):
        self.router_agent = RouterAgent()
        self.research_agent = ResearchAgent(vector_store, reranker)
        self.analysis_agent = AnalysisAgent()
        self.response_agent = ResponseAgent()
        self.verification_agent = VerificationAgent()

    async def run(self, state: AgentState, on_stage: Optional[Callable] = None) -> AgentState:
        """
        Executes the canonical pipeline.
        """
        start_time = time.time()
        
        def emit(stage: str, status: str, data: Any = None):
            if on_stage:
                on_stage(stage, status, data)
                
        try:
            # 1. Router Agent
            emit("classify", "active")
            result = await self.router_agent.run(state)
            if not result.success:
                raise Exception(result.error)
            
            qtype_val = state.query_type.value if hasattr(state.query_type, 'value') else state.query_type
            emit("classify", "complete", {"type": qtype_val})
            
            emit("reformulate", "active")
            emit("reformulate", "complete", {"sections": len(state.offense_sections)})

            # 2. Research Agent (Local + External Retrieval + Validation)
            emit("retrieve", "active")
            result = await self.research_agent.run(state)
            if not result.success:
                raise Exception(result.error)
                
            total_results = 0
            if state.validated_evidence:
                total_results = len(state.validated_evidence.statutory_results) + len(state.validated_evidence.case_law_results)
            
            emit("retrieve", "complete", {"results": total_results})
            emit("rerank", "active")
            emit("rerank", "complete")
            
            if "WebIntelAgent" in state.agents_used:
                emit("web_search", "active")
                emit("web_search", "complete")

            # 3. Analysis Agent (Confidence & Bail)
            emit("score", "active")
            result = await self.analysis_agent.run(state)
            if not result.success:
                raise Exception(result.error)
                
            emit("score", "complete", {
                "confidence": state.confidence_score, 
                "level": state.confidence_level
            })

            # 4. Response Agent (Grounded Generation)
            emit("generate", "active")
            result = await self.response_agent.run(state)
            if not result.success:
                raise Exception(result.error)
                
            emit("generate", "complete")

            # 5. Verification Agent (Claim Verification & Final Answer)
            emit("quality_review", "active")
            result = await self.verification_agent.run(state)
            if not result.success:
                raise Exception(result.error)
                
            emit("quality_review", "complete")
            
            # Post-processing / Enrichment mapping for UI
            elapsed_ms = int((time.time() - start_time) * 1000)
            state.processing_info["total_time_ms"] = elapsed_ms
            state.processing_info["agents_used"] = state.agents_used
            
        except Exception as e:
            logger.error(f"[AgentOrchestrator] Pipeline error: {e}", exc_info=True)
            state.final_answer = f"An error occurred during processing: {str(e)}"
            state.grounding_status = "fail"
            state.confidence_score = 0.0
            state.citations = []

        return state
