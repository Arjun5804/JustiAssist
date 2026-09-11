import pytest
from confidence_scorer import ConfidenceScorer, RetrievalConfidence
from dataclasses import dataclass
from typing import List

@dataclass
class MockResult:
    score: float
    section_number: str
    text: str

@dataclass
class MockReformulated:
    extracted_sections: List[str]

def test_confidence_high_score():
    scorer = ConfidenceScorer()
    
    results = [
        MockResult(0.95, "IPC_302", "Section 302 of IPC deals with murder..."),
        MockResult(0.88, "IPC_302", "Murder is punishable under IPC 302..."),
    ]
    reformulated = MockReformulated(extracted_sections=["IPC_302"])
    
    confidence = scorer.compute_confidence(
        query="What is IPC 302?",
        reformulated_query=reformulated,
        results=results,
        query_type="legal_info"
    )
    
    assert confidence.overall_score >= 0.8
    assert confidence.get_label() == "HIGH"
    assert confidence.section_coverage == 1.0

def test_confidence_low_score():
    scorer = ConfidenceScorer()
    
    results = [
        MockResult(0.3, "Unknown", "Some random text about something else..."),
    ]
    reformulated = MockReformulated(extracted_sections=["IPC_302"])
    
    confidence = scorer.compute_confidence(
        query="What is IPC 302?",
        reformulated_query=reformulated,
        results=results,
        query_type="legal_info"
    )
    
    assert confidence.overall_score < 0.5
    assert confidence.get_label() in ["LOW", "VERY LOW"]
    assert confidence.section_coverage == 0.0

def test_confidence_bail_completeness():
    scorer = ConfidenceScorer()
    
    # Missing CrPC 437/438/439
    results = [
        MockResult(0.8, "CrPC_436", "Bailable offences..."),
    ]
    reformulated = MockReformulated(extracted_sections=[])
    
    confidence = scorer.compute_confidence(
        query="How to get bail?",
        reformulated_query=reformulated,
        results=results,
        query_type="bail"
    )
    
    # completeness should be 1/4 = 0.25
    assert confidence.legal_completeness == 0.25
