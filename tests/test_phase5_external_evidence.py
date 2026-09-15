import pytest
import asyncio
from unittest.mock import patch, MagicMock
from retrieval.external import AuthorityClassifier, ExternalEvidenceNormalizer, ExternalRetriever
from retrieval.models import AuthorityLevel, ValidatedEvidenceSet, SearchResult, Provenance
from retrieval.evidence import EvidenceValidator
from generation.verification import ClaimVerifier
from generation.models import Claim, VerificationVerdict

def test_authority_classifier():
    assert AuthorityClassifier.classify("https://supreme.court.gov.in", "web") == AuthorityLevel.PRIMARY_OFFICIAL
    assert AuthorityClassifier.classify("https://indiankanoon.org/doc/123", "web") == AuthorityLevel.TRUSTED_LEGAL
    assert AuthorityClassifier.classify("https://thehindu.com/news", "web") == AuthorityLevel.NEWS
    assert AuthorityClassifier.classify("https://unknown.domain.com", "web") == AuthorityLevel.UNKNOWN
    assert AuthorityClassifier.classify("https://indiankanoon.org", "indian_kanoon") == AuthorityLevel.TRUSTED_LEGAL
    assert AuthorityClassifier.classify("https://news.com", "legal_news") == AuthorityLevel.NEWS

def test_external_evidence_normalizer_firecrawl():
    result = {
        "url": "https://indiankanoon.org/doc/123",
        "title": "BNS Section 45",
        "content": "This is the content."
    }
    
    sr = ExternalEvidenceNormalizer.normalize_firecrawl(result)
    assert sr.dataset_type == "external_web"
    assert sr.provenance.source_authority == AuthorityLevel.TRUSTED_LEGAL
    assert sr.chunk_id.startswith("ext_web_")
    assert sr.text == "This is the content."

@pytest.mark.asyncio
async def test_external_retriever_mocked():
    with patch("retrieval.external.ExternalRetriever._fetch_firecrawl", new_callable=MagicMock) as mock_firecrawl, \
         patch("retrieval.external.ExternalRetriever._fetch_kanoon", new_callable=MagicMock) as mock_kanoon, \
         patch("retrieval.external.ExternalRetriever._fetch_news", new_callable=MagicMock) as mock_news:
         
        mock_firecrawl.return_value = asyncio.Future()
        mock_firecrawl.return_value.set_result([{"url": "http://india.gov.in/law", "content": "law text"}])
        
        mock_kanoon.return_value = asyncio.Future()
        mock_kanoon.return_value.set_result([{"url": "http://indiankanoon.org/doc", "preview": "kanoon preview"}])
        
        mock_news.return_value = asyncio.Future()
        mock_news.return_value.set_result([{"url": "http://thehindu.com/news", "title": "News", "summary": "summary"}])
        
        results = await ExternalRetriever.retrieve(
            query="test",
            trigger_web_search=True,
            fetch_kanoon=True,
            fetch_news=True
        )
        
        assert len(results) == 3
        types = [r.dataset_type for r in results]
        assert "external_web" in types
        assert "indian_kanoon" in types
        assert "legal_news" in types
        
        for r in results:
            if r.dataset_type == "external_web":
                assert r.provenance.source_authority == AuthorityLevel.PRIMARY_OFFICIAL
            elif r.dataset_type == "indian_kanoon":
                assert r.provenance.source_authority == AuthorityLevel.TRUSTED_LEGAL
            elif r.dataset_type == "legal_news":
                assert r.provenance.source_authority == AuthorityLevel.NEWS

def test_evidence_validator_external_results():
    validator = EvidenceValidator()
    
    sr1 = SearchResult(
        chunk_id="ext_web_1",
        text="Duplicate content",
        score=0.0,
        law_type="Web",
        section_number="1",
        source_dataset="Firecrawl",
        dataset_type="external_web",
        metadata={},
        provenance=Provenance(source_authority=AuthorityLevel.TRUSTED_LEGAL)
    )
    
    sr2 = SearchResult(
        chunk_id="ext_web_2",
        text="Duplicate content",  # Same text and provenance should deduplicate
        score=0.0,
        law_type="Web",
        section_number="1",
        source_dataset="Firecrawl",
        dataset_type="external_web",
        metadata={},
        provenance=Provenance(source_authority=AuthorityLevel.TRUSTED_LEGAL)
    )
    
    evidence = ValidatedEvidenceSet(external_results=[sr1, sr2])
    validated = validator.validate(evidence)
    
    # Should deduplicate based on signature
    assert len(validated.external_results) == 1
    assert validated.external_results[0].chunk_id == "ext_web_1"

@pytest.mark.asyncio
async def test_claim_verifier_conflicting():
    verifier = ClaimVerifier()
    
    # Mock the LLM call in ClaimVerifier to return CONFLICTING
    with patch("generation.verification.call_llm", new_callable=MagicMock) as mock_llm:
        mock_llm.return_value = asyncio.Future()
        mock_llm.return_value.set_result('{"verdict": "CONFLICTING", "reason": "The evidence explicitly states the opposite."}')
        
        evidence = ValidatedEvidenceSet(
            external_results=[
                SearchResult(
                    chunk_id="ext_1",
                    text="The law states that X is illegal.",
                    score=0.0,
                    law_type="Web",
                    section_number="1",
                    source_dataset="Firecrawl",
                    dataset_type="external_web",
                    metadata={}
                )
            ]
        )
        
        claim = Claim(claim_id="c1", text="The law states that X is completely legal.", evidence_ids=["ext_1"])
        
        verifications = await verifier.verify_claims([claim], evidence)
        
        assert len(verifications) == 1
        assert verifications[0].verdict == VerificationVerdict.CONFLICTING
