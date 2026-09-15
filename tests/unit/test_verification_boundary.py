import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agents.state import AgentState
from agents.response_agent import ResponseAgent
from agents.verification_agent import VerificationAgent
from retrieval.models import SearchResult, ValidatedEvidenceSet
from generation.models import GeneratedResponse, Claim, ClaimVerification, VerificationVerdict

@pytest.fixture
def base_state():
    state = AgentState(query="test")
    state.validated_evidence = ValidatedEvidenceSet(
        statutory_results=[
            SearchResult(chunk_id="doc1", text="text1", score=1.0, law_type="statute", section_number="1", source_dataset="test", dataset_type="test", metadata={}, provenance=MagicMock())
        ],
        case_law_results=[],
        session_documents=[],
        external_results=[]
    )
    return state

@pytest.mark.asyncio
async def test_verification_result_propagation(base_state):
    """Test 1: verify ResponseAgent propagates verification results to AgentState"""
    agent = ResponseAgent()
    
    mock_verifications = [
        ClaimVerification(claim_id="c1", verdict=VerificationVerdict.SUPPORTED, evidence_ids=["doc1"])
    ]
    mock_response = GeneratedResponse(
        answer="Supported answer",
        claims=[Claim(claim_id="c1", text="statement", evidence_ids=["doc1"])],
        verifications=mock_verifications
    )
    
    agent.pipeline.run = AsyncMock(return_value=mock_response)
    
    result = await agent.run(base_state)
    assert result.success
    assert result.state.generated_response is not None
    assert result.state.generated_response.verifications == mock_verifications

@pytest.mark.asyncio
async def test_unsupported_claim_cannot_pass(base_state):
    """Test 2: verify VerificationAgent rejects states with unsupported claims"""
    base_state.has_generated = True
    base_state.generated_response = GeneratedResponse(
        answer="Unsupported answer",
        claims=[Claim(claim_id="c1", text="statement", evidence_ids=["doc1"])],
        verifications=[
            ClaimVerification(claim_id="c1", verdict=VerificationVerdict.UNSUPPORTED, evidence_ids=["doc1"])
        ]
    )
    
    agent = VerificationAgent()
    result = await agent.run(base_state)
    
    assert result.success
    # The agent should overwrite the answer with the abstention fallback
    assert "does not sufficiently support" in result.state.final_answer
    assert result.state.citations == []
    assert result.state.grounding_status == "fail"
    # Even if we reject it, has_verified becomes true as the gate functioned
    assert result.state.has_verified

@pytest.mark.asyncio
async def test_evidence_id_is_not_sufficient(base_state):
    """Test 3: verify presence of evidence ID doesn't bypass verification check"""
    base_state.has_generated = True
    base_state.generated_response = GeneratedResponse(
        answer="Invalid answer",
        claims=[Claim(claim_id="c1", text="statement", evidence_ids=["doc1"])], # Has valid evidence_id
        # BUT verification verdict is INVALID_REFERENCE
        verifications=[
            ClaimVerification(claim_id="c1", verdict=VerificationVerdict.INVALID_REFERENCE, evidence_ids=["doc1"])
        ]
    )
    
    agent = VerificationAgent()
    result = await agent.run(base_state)
    
    assert result.success
    assert "does not sufficiently support" in result.state.final_answer
    assert len(result.state.citations) == 0
    assert result.state.grounding_status == "fail"

@pytest.mark.asyncio
async def test_abstention(base_state):
    """Test 4: verify abstention handles correctly without claims"""
    base_state.has_generated = True
    base_state.generated_response = GeneratedResponse(
        answer="I cannot answer this.",
        claims=[],
        is_abstention=True,
        verifications=[]
    )
    
    agent = VerificationAgent()
    result = await agent.run(base_state)
    
    assert result.success
    assert result.state.final_answer == "I cannot answer this."
    assert len(result.state.citations) == 0
    assert result.state.grounding_status == "fail"
    assert result.state.has_verified
