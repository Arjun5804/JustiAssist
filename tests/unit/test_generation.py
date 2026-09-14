import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
from retrieval.models import ValidatedEvidenceSet, SearchResult, Claim
from generation.models import GeneratedResponse, ClaimVerification, VerificationVerdict
from generation.generator import GroundedGenerator
from generation.verification import ClaimVerifier
from generation.pipeline import GroundedGenerationPipeline

@pytest.fixture
def sample_evidence():
    return ValidatedEvidenceSet(
        statutory_results=[
            SearchResult(
                chunk_id="chunk_1",
                text="The penalty for theft is 3 years.",
                section_number="378",
                source_dataset="BNS",
                law_type="statutory",
                score=0.9,
                dataset_type="statutory",
                metadata={}
            )
        ],
        case_law_results=[
            SearchResult(
                chunk_id="chunk_2",
                text="Bail granted because the penalty is under 7 years.",
                section_number="436",
                source_dataset="BNSS",
                law_type="case_law",
                score=0.85,
                dataset_type="case_law",
                metadata={}
            )
        ],
        session_documents=[]
    )

@pytest.mark.asyncio
async def test_generator_valid_json():
    generator = GroundedGenerator()
    with patch("generation.generator.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '''```json
        {
            "answer": "The penalty is 3 years.",
            "claims": [{"claim_id": "c1", "text": "Penalty is 3 years", "evidence_ids": ["chunk_1"]}]
        }
        ```'''
        response = await generator.generate_response("query", ValidatedEvidenceSet())
        assert response.answer == "The penalty is 3 years."
        assert len(response.claims) == 1
        assert response.claims[0].evidence_ids == ["chunk_1"]

@pytest.mark.asyncio
async def test_verifier_deterministic_checks(sample_evidence):
    verifier = ClaimVerifier()
    
    # 1. Missing text
    empty_claim = Claim(claim_id="1", text="", evidence_ids=["chunk_1"])
    res = await verifier.verify_claims([empty_claim], sample_evidence)
    assert res[0].verdict == VerificationVerdict.UNSUPPORTED
    
    # 2. Missing citations
    no_cite_claim = Claim(claim_id="2", text="Penalty is 3 years", evidence_ids=[])
    res = await verifier.verify_claims([no_cite_claim], sample_evidence)
    assert res[0].verdict == VerificationVerdict.UNSUPPORTED
    
    # 3. Invalid reference
    invalid_cite_claim = Claim(claim_id="3", text="Penalty is 3 years", evidence_ids=["chunk_99"])
    res = await verifier.verify_claims([invalid_cite_claim], sample_evidence)
    assert res[0].verdict == VerificationVerdict.INVALID_REFERENCE
    
@pytest.mark.asyncio
async def test_verifier_semantic_check(sample_evidence):
    verifier = ClaimVerifier()
    
    claim = Claim(claim_id="c1", text="Penalty is 3 years", evidence_ids=["chunk_1"])
    
    with patch("generation.verification.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"verdict": "SUPPORTED", "reason": "Match"}'
        res = await verifier.verify_claims([claim], sample_evidence)
        assert res[0].verdict == VerificationVerdict.SUPPORTED
        
        mock_llm.return_value = '{"verdict": "PARTIALLY_SUPPORTED", "reason": "Half match"}'
        res = await verifier.verify_claims([claim], sample_evidence)
        assert res[0].verdict == VerificationVerdict.PARTIALLY_SUPPORTED

@pytest.mark.asyncio
async def test_pipeline_successful_revision(sample_evidence):
    pipeline = GroundedGenerationPipeline(max_retries=2)
    
    # Mock generator to return unsupported first, then supported
    mock_responses = [
        GeneratedResponse(
            answer="Attempt 1",
            claims=[Claim(claim_id="c1", text="False claim", evidence_ids=["chunk_1"])]
        ),
        GeneratedResponse(
            answer="Attempt 2",
            claims=[Claim(claim_id="c1", text="True claim", evidence_ids=["chunk_1"])]
        )
    ]
    
    # Mock verifier to fail first, then pass
    mock_verifications = [
        [ClaimVerification(claim_id="c1", verdict=VerificationVerdict.UNSUPPORTED)],
        [ClaimVerification(claim_id="c1", verdict=VerificationVerdict.SUPPORTED)]
    ]
    
    pipeline.generator.generate_response = AsyncMock(side_effect=mock_responses)
    pipeline.verifier.verify_claims = AsyncMock(side_effect=mock_verifications)
    
    result = await pipeline.run("test", sample_evidence)
    
    assert result.answer == "Attempt 2"
    assert not result.is_abstention
    assert pipeline.generator.generate_response.call_count == 2
    assert pipeline.verifier.verify_claims.call_count == 2

@pytest.mark.asyncio
async def test_pipeline_failed_revision_to_abstention(sample_evidence):
    pipeline = GroundedGenerationPipeline(max_retries=2)
    
    # Mock generator to always return something
    pipeline.generator.generate_response = AsyncMock(return_value=GeneratedResponse(
        answer="Attempt",
        claims=[Claim(claim_id="c1", text="False claim", evidence_ids=["chunk_1"])]
    ))
    
    # Mock verifier to always fail
    pipeline.verifier.verify_claims = AsyncMock(return_value=[
        ClaimVerification(claim_id="c1", verdict=VerificationVerdict.UNSUPPORTED)
    ])
    
    result = await pipeline.run("test", sample_evidence)
    
    assert result.is_abstention
    assert result.answer == "The available retrieved evidence does not sufficiently support a reliable answer."
    assert pipeline.generator.generate_response.call_count == 2
    
@pytest.mark.asyncio
async def test_pipeline_no_evidence():
    pipeline = GroundedGenerationPipeline()
    empty_evidence = ValidatedEvidenceSet(statutory_results=[], case_law_results=[])
    
    result = await pipeline.run("test", empty_evidence)
    assert result.is_abstention
    assert result.answer == "The available retrieved evidence does not sufficiently support a reliable answer."
