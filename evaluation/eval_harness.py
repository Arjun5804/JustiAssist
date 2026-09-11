"""
JustiAssist Evaluation Harness
Offline testing and metrics calculation for RAG pipeline
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
import numpy as np

# Add parent directory to path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    VECTOR_STORE_PATH,
    TOP_K_STATUTORY,
    ConfidenceLevel
)
from vector_store import VectorStore
from confidence_scorer import ConfidenceScorer, RetrievalConfidence
from citation_validator import CitationValidator, CitationValidation


@dataclass
class TestCase:
    """Evaluation test case"""
    id: str
    query: str
    expected_sections: List[str]  # e.g. ["302", "300"]
    ground_truth_answer: str = ""
    min_confidence: str = "medium"  # high, medium, low


class EvalHarness:
    """
    Offline evaluation harness for JustiAssist.
    Tests retrieval accuracy and confidence scoring.
    """
    
    def __init__(self):
        print("Initializing Evaluation Harness...")
        self.vector_store = VectorStore()
        if not self.vector_store.load(VECTOR_STORE_PATH):
            raise RuntimeError("Could not load vector store. Run build_indices.py first.")
            
        self.confidence_scorer = ConfidenceScorer()
        self.citation_validator = CitationValidator()
        
    def run_suite(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """Run full evaluation suite"""
        results = {
            "total": len(test_cases),
            "retrieval_hits": 0,
            "retrieval_mrr": 0.0,
            "confidence_alignment": 0,
            "details": []
        }
        
        print(f"\nRunning {len(test_cases)} test cases...\n")
        
        for case in test_cases:
            case_result = self._evaluate_case(case)
            results["details"].append(case_result)
            
            if case_result["retrieval_hit"]:
                results["retrieval_hits"] += 1
            results["retrieval_mrr"] += case_result["mrr"]
            if case_result["confidence_aligned"]:
                results["confidence_alignment"] += 1
                
        # Calculate aggregates
        if results["total"] > 0:
            results["retrieval_hit_rate"] = results["retrieval_hits"] / results["total"]
            results["retrieval_mrr"] = results["retrieval_mrr"] / results["total"]
            results["confidence_accuracy"] = results["confidence_alignment"] / results["total"]
        
        return results
    
    def _evaluate_case(self, case: TestCase) -> Dict[str, Any]:
        """Evaluate single test case"""
        print(f"Testing: {case.query[:50]}...")
        
        # 1. Run Hybrid Search
        results = self.vector_store.hybrid_search_statutory(
            case.query,
            top_k=TOP_K_STATUTORY * 2
        )
        
        # 2. Check Retrieval
        retrieved_sections = [r.section_number for r in results]
        hit = False
        rank = 0
        
        for expected in case.expected_sections:
            # Flexible matching (e.g. "302" in "IPC 302")
            for i, actual in enumerate(retrieved_sections):
                if expected in actual:
                    hit = True
                    rank = i + 1
                    break
            if hit:
                break
                
        mrr = 1.0 / rank if rank > 0 else 0.0
        
        # 3. Check Confidence
        # (Mocking reformulator for standalone test)
        from dataclasses import dataclass
        @dataclass
        class MockReformulator:
            search_terms = case.query.split()
            extracted_sections = []
        
        confidence = self.confidence_scorer.compute_confidence(
            query=case.query,
            reformulated_query=MockReformulator(),
            results=results[:TOP_K_STATUTORY],
            query_type="legal_info"
        )
        
        from config import get_confidence_level
        level = get_confidence_level(confidence.overall_score)
        
        # Check alignment (simplified)
        expected_level_val = {
            "high": 3, "medium": 2, "low": 1, "very_low": 0
        }.get(case.min_confidence, 0)
        
        actual_level_val = {
            "high": 3, "medium": 2, "low": 1, "very_low": 0
        }.get(level.value, 0)
        
        aligned = actual_level_val >= expected_level_val
        
        return {
            "id": case.id,
            "retrieval_hit": hit,
            "rank": rank,
            "mrr": mrr,
            "retrieved_top_3": retrieved_sections[:3],
            "confidence_score": round(confidence.overall_score, 2),
            "confidence_level": level.value,
            "confidence_aligned": aligned
        }

# Define standard test suite
STANDARD_TEST_SUITE = [
    TestCase(
        id="T1",
        query="What is the punishment for murder?",
        expected_sections=["302", "103"], # IPC 302 or BNS 103
        min_confidence="high"
    ),
    TestCase(
        id="T2",
        query="Can I get bail for non-bailable offense?",
        expected_sections=["437"], # CrPC 437
        min_confidence="medium"
    ),
    TestCase(
        id="T3",
        query="procedure for arrest by police without warrant",
        expected_sections=["41"], # CrPC 41 or BNSS 35
        min_confidence="high"
    ),
    TestCase(
        id="T4", # Ambiguous/Complex
        query="what if police refuses to register fir",
        expected_sections=["154"], # CrPC 154(3)
        min_confidence="medium"
    )
]

if __name__ == "__main__":
    harness = EvalHarness()
    results = harness.run_suite(STANDARD_TEST_SUITE)
    
    print("\n" + "="*40)
    print("EVALUATION RESULTS")
    print("="*40)
    print(f"Total Cases: {results['total']}")
    print(f"Hit Rate:    {results.get('retrieval_hit_rate', 0):.2%}")
    print(f"MRR:         {results.get('retrieval_mrr', 0):.2f}")
    print(f"Confidence:  {results.get('confidence_accuracy', 0):.2%}")
    print("\nDetails:")
    for detail in results['details']:
        status = "✅" if detail['retrieval_hit'] else "❌"
        print(f"{status} {detail['id']}: Rank {detail['rank']} | Conf: {detail['confidence_level']} (Sc: {detail['confidence_score']}) | Top: {detail['retrieved_top_3']}")
