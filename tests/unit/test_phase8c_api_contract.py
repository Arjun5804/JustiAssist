import pytest
from typing import List

from agents.state import AgentState, AgentResult
from agents.query_classifier import QueryType
from agents.verification_agent import VerificationAgent
from generation.models import GeneratedResponse, Claim, ClaimVerification, VerificationVerdict
from api.query import _state_to_response, QueryResponse, VerificationSummary
from retrieval.models import ValidatedEvidenceSet, SearchResult

@pytest.fixture
def base_state():
    state = AgentState(query="Test query")
    state.query_type = QueryType.LEGAL_INFO
    state.has_generated = True
    
    # Setup some valid evidence for the verification agent
    state.validated_evidence = ValidatedEvidenceSet(
        statutory_results=[
            SearchResult(
                chunk_id="chunk-1",
                text="The law says X.",
                score=0.9,
                law_type="ipc",
                section_number="Sec 1",
                source_dataset="ipc.csv",
                dataset_type="statutory",
                metadata={}
            )
        ],
        case_law_results=[],
        session_documents=[]
    )
    return state

# Test 1 - default state
def test_default_agent_state():
    state = AgentState(query="Test query")
    assert state.is_abstention is False

# Test 2 - accepted answer
@pytest.mark.asyncio
async def test_accepted_answer_is_not_abstention(base_state):
    # Setup a fully verified response
    claim = Claim(claim_id="claim-1", text="The law says X", evidence_ids=["chunk-1"])
    verification = ClaimVerification(
        claim_id="claim-1", 
        verdict=VerificationVerdict.SUPPORTED, 
        evidence_ids=["chunk-1"]
    )
    
    base_state.generated_response = GeneratedResponse(
        answer="The law says X.",
        claims=[claim],
        verifications=[verification]
    )
    
    agent = VerificationAgent()
    result = await agent.run(base_state)
    
    assert result.success is True
    assert result.state.is_abstention is False
    assert result.state.grounding_status != "fail"

# Test 3 - final abstention
@pytest.mark.asyncio
async def test_rejected_answer_is_abstention(base_state):
    # Setup a rejected response (unsupported claim)
    claim = Claim(claim_id="claim-1", text="The law says Y", evidence_ids=["chunk-1"])
    verification = ClaimVerification(
        claim_id="claim-1", 
        verdict=VerificationVerdict.UNSUPPORTED, 
        evidence_ids=["chunk-1"]
    )
    
    base_state.generated_response = GeneratedResponse(
        answer="The law says Y.",
        claims=[claim],
        verifications=[verification]
    )
    
    agent = VerificationAgent()
    result = await agent.run(base_state)
    
    assert result.success is True
    assert result.state.is_abstention is True
    assert result.state.grounding_status == "fail"
    assert result.state.final_answer == "The available retrieved evidence does not sufficiently support a reliable answer."

# Test 4 - verification mapping
def test_verification_mapping():
    state = AgentState(query="Test query")
    state.query_type = QueryType.LEGAL_INFO
    
    verifications = [
        ClaimVerification(
            claim_id="claim-1",
            verdict=VerificationVerdict.SUPPORTED,
            evidence_ids=["chunk-1", "chunk-2"]
        )
    ]
    
    state.generated_response = GeneratedResponse(
        answer="The answer is X.",
        verifications=verifications
    )
    
    response = _state_to_response(state)
    
    assert response.is_abstention is False
    assert len(response.verification_verdicts) == 1
    
    summary = response.verification_verdicts[0]
    assert summary.claim_id == "claim-1"
    assert summary.verdict == "SUPPORTED"
    assert summary.evidence_ids == ["chunk-1", "chunk-2"]

# Test 5 - no generated response
def test_no_generated_response():
    state = AgentState(query="Test query")
    state.query_type = QueryType.LEGAL_INFO
    state.generated_response = None
    
    response = _state_to_response(state)
    
    assert response.is_abstention is False
    assert isinstance(response.verification_verdicts, list)
    assert len(response.verification_verdicts) == 0

# Test 6 - abstention API contract
def test_abstention_api_contract():
    state = AgentState(query="Test query")
    state.query_type = QueryType.LEGAL_INFO
    state.is_abstention = True
    
    response = _state_to_response(state)
    assert response.is_abstention is True

# Test 7 - normal API contract
def test_normal_api_contract():
    state = AgentState(query="Test query")
    state.query_type = QueryType.LEGAL_INFO
    state.is_abstention = False
    state.final_answer = "Valid answer"
    
    response = _state_to_response(state)
    assert response.is_abstention is False
    assert response.answer == "Valid answer"
    assert hasattr(response, "verification_verdicts")
    assert isinstance(response.verification_verdicts, list)
