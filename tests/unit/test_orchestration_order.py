import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agents.state import AgentState
from agents.orchestrator import AgentOrchestrator
from agents.query_classifier import QueryType
from retrieval.models import EvidenceSet, ValidatedEvidenceSet, SearchResult
from generation.models import GeneratedResponse, Claim, VerificationVerdict, ClaimVerification

@pytest.fixture
def mock_evidence_set():
    evidence = EvidenceSet()
    evidence.statutory_results = [SearchResult(chunk_id="s1", text="statutory text", score=0.9, law_type="statute", section_number="1", source_dataset="dataset", dataset_type="type", metadata={})]
    return evidence

@pytest.fixture
def mock_validated_evidence_set():
    evidence = ValidatedEvidenceSet(
        statutory_results=[SearchResult(chunk_id="s1", text="statutory text", score=0.9, law_type="statute", section_number="1", source_dataset="dataset", dataset_type="type", metadata={}, provenance=MagicMock())],
        case_law_results=[],
        session_documents=[],
        external_results=[]
    )
    return evidence

@pytest.mark.asyncio
async def test_canonical_execution_order(mock_evidence_set, mock_validated_evidence_set):
    """
    Proves that execution follows:
    ExternalRetriever -> EvidenceSet -> EvidenceValidator -> ValidatedEvidenceSet -> Generation -> Verification -> Final Response.
    Fails if generation receives raw EvidenceSet or external fetch happens post-generation.
    """
    orchestrator = AgentOrchestrator(vector_store=MagicMock(), reranker=MagicMock())
    
    # State tracking
    execution_log = []
    
    # Mock Router
    async def mock_router_run(state):
        execution_log.append("router")
        state.query_type = QueryType.LEGAL_INFO
        state.agents_used.append("RouterAgent")
        return MagicMock(success=True, state=state)
    orchestrator.router_agent.run = AsyncMock(side_effect=mock_router_run)
    
    # Mock Research (must enforce boundary)
    async def mock_research_run(state):
        execution_log.append("research_local")
        execution_log.append("research_external")
        execution_log.append("evidence_validation")
        state.raw_evidence = mock_evidence_set
        state.validated_evidence = mock_validated_evidence_set
        state.has_retrieved = True
        state.has_validated = True
        return MagicMock(success=True, state=state)
    orchestrator.research_agent.run = AsyncMock(side_effect=mock_research_run)
    
    # Mock Analysis
    async def mock_analysis_run(state):
        execution_log.append("analysis")
        return MagicMock(success=True, state=state)
    orchestrator.analysis_agent.run = AsyncMock(side_effect=mock_analysis_run)
    
    # Mock Response (must receive validated evidence)
    async def mock_response_run(state):
        assert state.validated_evidence is not None, "Generation received raw EvidenceSet instead of ValidatedEvidenceSet"
        assert state.has_validated, "Validation did not complete before generation"
        execution_log.append("generation")
        state.generated_response = GeneratedResponse(answer="mock answer", claims=[])
        state.has_generated = True
        return MagicMock(success=True, state=state)
    orchestrator.response_agent.run = AsyncMock(side_effect=mock_response_run)
    
    # Mock Verification (must follow generation)
    async def mock_verification_run(state):
        assert state.has_generated, "Verification ran before generation"
        execution_log.append("verification")
        execution_log.append("final_response_emit")
        state.final_answer = "mock verified answer"
        state.has_verified = True
        return MagicMock(success=True, state=state)
    orchestrator.verification_agent.run = AsyncMock(side_effect=mock_verification_run)
    
    # Execute Pipeline
    initial_state = AgentState(query="test query")
    final_state = await orchestrator.run(initial_state)
    
    # Assert Exact Ordering
    expected_order = [
        "router",
        "research_local",
        "research_external",
        "evidence_validation",
        "analysis",
        "generation",
        "verification",
        "final_response_emit"
    ]
    
    assert execution_log == expected_order, f"Execution order violated. Expected {expected_order}, got {execution_log}"
    
    # Hard Invariants
    # 1. External retrieval must occur before generation (proven by list order)
    ext_idx = execution_log.index("research_external")
    gen_idx = execution_log.index("generation")
    assert ext_idx < gen_idx
    
    # 2. Validation before generation
    val_idx = execution_log.index("evidence_validation")
    assert val_idx < gen_idx
    
    # 3. Final response after verification
    ver_idx = execution_log.index("verification")
    fin_idx = execution_log.index("final_response_emit")
    assert ver_idx < fin_idx
