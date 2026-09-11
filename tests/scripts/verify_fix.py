from confidence_scorer import ConfidenceScorer, RetrievalConfidence
from dataclasses import dataclass
from typing import List, Any

# Mock classes to simulate main app structures
@dataclass
class MockResult:
    score: float
    section_number: str
    text: str

@dataclass
class MockReformulated:
    extracted_sections: List[str]

def test_fix():
    print("Initializing ConfidenceScorer...")
    scorer = ConfidenceScorer()
    
    # Simulate the "Explain IPC 297" scenario
    # 1. We extracted [IPC_297] from query
    reformulated = MockReformulated(extracted_sections=["IPC_297"])
    
    # 2. We retrieved IPC 297 chunks (good section match)
    # But text lacks "bail", "punishment" keywords to trigger Intent Matching
    results = [
        MockResult(0.65, "IPC_297", "Trespassing on burial places, etc..."),
        MockResult(0.60, "IPC_297", "Whoever, with the intention of wounding..."),
    ]
    
    print("\n---------------------------------------------------")
    print("SCENARIO: Query 'Explain IPC 297'")
    print(" - Requested: ['IPC_297']")
    print(" - Retrieved: 2 chunks for IPC_297")
    print(" - Intent Keywords: NONE (simulating low semantic keyword match)")
    print("---------------------------------------------------")
    
    confidence = scorer.compute_confidence(
        query="Explain IPC 297",
        reformulated_query=reformulated,
        results=results,
        query_type="legal_info"
    )
    
    print(f"\nFinal Overall Score: {confidence.overall_score:.3f}")
    print(f"Confidence Label: {confidence.get_label()}")
    
    print("\nBreakdown:")
    print(f"  Section Coverage: {confidence.section_coverage:.2f}")
    print(f"  Intent Matching: {confidence.intent_matching:.2f}") 
    # Intent likely low because text doesn't have terms from LEGAL_CONCEPTS dictionary
    
    if confidence.overall_score >= 0.85:
        print("\n✅ SUCCESS: Confidence bumped to HIGH (>= 0.85) due to Section Override!")
    else:
        print("\n❌ FAILURE: Confidence score still too low.")

if __name__ == "__main__":
    test_fix()
