"""
JustiAssist Enhanced Confidence Scoring
Multi-factor retrieval confidence beyond simple similarity averaging
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import re


@dataclass
class RetrievalConfidence:
    """Detailed confidence breakdown"""
    overall_score: float  # 0-1
    section_coverage: float  # 0-1
    intent_matching: float  # 0-1
    source_redundancy: float  # 0-1
    legal_completeness: float  # 0-1
    avg_relevance: float  # 0-1
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            'overall_score': round(self.overall_score, 3),
            'section_coverage': round(self.section_coverage, 3),
            'intent_matching': round(self.intent_matching, 3),
            'source_redundancy': round(self.source_redundancy, 3),
            'legal_completeness': round(self.legal_completeness, 3),
            'avg_relevance': round(self.avg_relevance, 3),
            'metadata': self.metadata,
        }
    
    def get_label(self) -> str:
        """Get confidence level label"""
        if self.overall_score >= 0.8:
            return "HIGH"
        elif self.overall_score >= 0.6:
            return "MEDIUM"
        elif self.overall_score >= 0.4:
            return "LOW"
        else:
            return "VERY LOW"


class ConfidenceScorer:
    """
    Computes multi-factor retrieval confidence for legal RAG.
    
    Factors:
    1. Section Coverage - Are requested sections present?
    2. Intent Matching - Do chunks cover query's legal concepts?
    3. Source Redundancy - Is info confirmed by multiple chunks?
    4. Legal Completeness - For bail, are required provisions present?
    5. Average Relevance - Mean similarity score
    
    Philosophy: High confidence when multiple independent signals align
    """
    
    # Required provisions for different query types
    REQUIRED_PROVISIONS = {
        'bail': ['CrPC_436', 'CrPC_437', 'CrPC_438', 'CrPC_439'],
        'bail_anticipatory': ['CrPC_438'],
        'bail_regular': ['CrPC_437'],
        'bail_default': ['CrPC_167'],
    }
    
    # Legal concept keywords (for intent matching)
    LEGAL_CONCEPTS = {
        'bail': ['bail', 'release', 'custody', 'liberty', 'bond', 'surety'],
        'punishment': ['punishment', 'sentence', 'imprisonment', 'fine', 'penalty'],
        'procedure': ['procedure', 'process', 'investigation', 'trial', 'hearing'],
        'rights': ['right', 'fundamental', 'constitutional', 'liberty', 'freedom'],
        'offence': ['offence', 'crime', 'violation', 'breach', 'criminal act', 'punishable', 'penalized'],
        'violent_crime': ['murder', 'assault', 'attack', 'kill', 'hurt', 'injury', 'violence'],
        'property_crime': ['theft', 'snatching', 'robbery', 'burglary', 'extortion', 'stole', 'stolen'],
        'sexual_offence': ['rape', 'harassment', 'molestation', 'voyeurism', 'stalking'],
    }
    
    def compute_confidence(
        self,
        query: str,
        reformulated_query: Any,  # ReformulatedQuery from query_reformulator
        results: List[Any],
        query_type: str = 'general'
    ) -> RetrievalConfidence:
        """
        Compute retrieval confidence with detailed breakdown.
        
        Args:
            query: Original user query
            reformulated_query: Enhanced query from reformulator
            results: Search results from vector store
            query_type: Type of query ('bail', 'legal_info', etc.)
            
        Returns:
            RetrievalConfidence with detailed scoring
        """
        if not results:
            return RetrievalConfidence(
                overall_score=0.0,
                section_coverage=0.0,
                intent_matching=0.0,
                source_redundancy=0.0,
                legal_completeness=0.0,
                avg_relevance=0.0,
                metadata={'reason': 'no_results'}
            )
        
        # 1. Section Coverage
        section_coverage = self._compute_section_coverage(
            reformulated_query.extracted_sections,
            results
        )
        
        # 2. Intent Matching
        intent_matching = self._compute_intent_matching(query, results)
        
        # 3. Source Redundancy
        source_redundancy = self._compute_source_redundancy(results)
        
        # 4. Legal Completeness
        legal_completeness = self._compute_legal_completeness(
            query_type,
            results
        )
        
        # 5. Average Relevance (semantic similarity)
        avg_relevance = sum(r.score for r in results) / len(results)
        
        # Compute weighted overall score
        overall_score = self._compute_overall_score(
            section_coverage=section_coverage,
            intent_matching=intent_matching,
            source_redundancy=source_redundancy,
            legal_completeness=legal_completeness,
            avg_relevance=avg_relevance,
            query_type=query_type
        )
        
        return RetrievalConfidence(
            overall_score=overall_score,
            section_coverage=section_coverage,
            intent_matching=intent_matching,
            source_redundancy=source_redundancy,
            legal_completeness=legal_completeness,
            avg_relevance=avg_relevance,
            metadata={
                'num_results': len(results),
                'query_type': query_type,
                'sections_requested': reformulated_query.extracted_sections,
                'top_score': results[0].score if results else 0.0,
            }
        )
    
    def _compute_section_coverage(
        self,
        requested_sections: List[str],
        results: List[Any]
    ) -> float:
        """
        Measure coverage of requested sections in results.
        Returns: 0-1 score
        """
        if not requested_sections:
            return 1.0  # No sections requested = full coverage
        
        found_sections = set()
        for result in results:
            section = getattr(result, 'section_number', '').upper()
            for req_sec in requested_sections:
                if req_sec.upper() in section:
                    found_sections.add(req_sec.upper())
        
        coverage = len(found_sections) / len(requested_sections)
        return coverage
    
    def _compute_intent_matching(
        self,
        query: str,
        results: List[Any]
    ) -> float:
        """
        Measure how well results match query's legal concepts.
        Returns: 0-1 score
        """
        query_lower = query.lower()
        
        # Identify query concepts
        query_concepts = []
        for concept_type, keywords in self.LEGAL_CONCEPTS.items():
            if any(kw in query_lower for kw in keywords):
                query_concepts.append(concept_type)
        
        if not query_concepts:
            return 0.7  # Neutral score if no specific concepts detected
        
        # Check if results contain these concepts
        concept_matches = 0
        for concept_type in query_concepts:
            keywords = self.LEGAL_CONCEPTS[concept_type]
            for result in results[:5]:  # Check top 5 results
                text_lower = getattr(result, 'text', '').lower()
                if any(kw in text_lower for kw in keywords):
                    concept_matches += 1
                    break  # Count once per concept
        
        intent_score = concept_matches / len(query_concepts)
        return intent_score
    
    def _compute_source_redundancy(self, results: List[Any]) -> float:
        """
        Measure information redundancy across multiple sources.
        Higher redundancy = higher confidence (multiple sources agree)
        Returns: 0-1 score
        """
        if len(results) < 2:
            return 0.5  # Not enough results for redundancy check
        
        # Group results by law_type and section
        section_frequency = {}
        for result in results:
            section = getattr(result, 'section_number', 'Unknown')
            section_frequency[section] = section_frequency.get(section, 0) + 1
        
        # Score based on how many results reference same sections
        repeated_sections = sum(1 for count in section_frequency.values() if count > 1)
        redundancy_score = min(repeated_sections / 3.0, 1.0)  # Cap at 3 repeated sections
        
        return redundancy_score
    
    def _compute_legal_completeness(
        self,
        query_type: str,
        results: List[Any]
    ) -> float:
        """
        For specific query types (e.g., bail), check if required provisions are present.
        Returns: 0-1 score
        """
        required_provisions = self.REQUIRED_PROVISIONS.get(query_type, [])
        
        if not required_provisions:
            return 1.0  # No specific requirements = complete
        
        found_provisions = set()
        for result in results:
            section = getattr(result, 'section_number', '').upper()
            for prov in required_provisions:
                if prov.upper() in section:
                    found_provisions.add(prov.upper())
        
        completeness = len(found_provisions) / len(required_provisions)
        return completeness
    
    def _compute_overall_score(
        self,
        section_coverage: float,
        intent_matching: float,
        source_redundancy: float,
        legal_completeness: float,
        avg_relevance: float,
        query_type: str
    ) -> float:
        """
        Compute weighted overall confidence score.
        Weights vary by query type for optimal precision.
        """
        if query_type in ['bail', 'bail_anticipatory', 'bail_regular']:
            # For bail queries, completeness is critical
            weights = {
                'section_coverage': 0.20,
                'intent_matching': 0.15,
                'source_redundancy': 0.10,
                'legal_completeness': 0.35,  # Most important for bail
                'avg_relevance': 0.20,
            }
        else:
            # For general legal queries, section coverage is critical
            weights = {
                'section_coverage': 0.35,  # Most important for general queries
                'intent_matching': 0.20,
                'source_redundancy': 0.15,
                'legal_completeness': 0.05,
                'avg_relevance': 0.25,
            }
        
        overall = (
            weights['section_coverage'] * section_coverage +
            weights['intent_matching'] * intent_matching +
            weights['source_redundancy'] * source_redundancy +
            weights['legal_completeness'] * legal_completeness +
            weights['avg_relevance'] * avg_relevance
        )
        
        # QUALITY OVERRIDE: 
        # If we found exactly what the user asked for (Section Coverage > 0.9),
        # force High Confidence (0.85+) regardless of intent/keywords.
        # This fixes issues where direct queries like "Explain IPC 297" fail 
        # because they lack "legal concept" keywords.
        if section_coverage >= 0.9:
            overall = max(overall, 0.85)
            
        # SECONDARY OVERRIDE:
        # If semantic relevance is very high (>0.75), trust the vector store
        # even if specific keywords are missing.
        if avg_relevance > 0.75:
            overall = max(overall, 0.75)
            
        return overall
    
    def should_use_gpt4_fallback(
        self,
        confidence: RetrievalConfidence,
        threshold: float = 0.5
    ) -> Tuple[bool, str]:
        """
        Determine if GPT-4 fallback should be used based on confidence.
        
        Args:
            confidence: RetrievalConfidence object
            threshold: Confidence threshold below which to fallback
            
        Returns:
            (should_fallback: bool, reason: str)
        """
        if confidence.overall_score >= threshold:
            return (False, "Confidence sufficient for grounded response")
        
        # Identify specific confidence issues
        reasons = []
        if confidence.section_coverage < 0.7:
            reasons.append("requested sections not found in context")
        if confidence.intent_matching < 0.6:
            reasons.append("retrieved chunks don't match query intent")
        if confidence.legal_completeness < 0.5:
            reasons.append("required legal provisions missing")
        
        reason_text = ", ".join(reasons) if reasons else "overall confidence too low"
        return (True, f"Low retrieval confidence: {reason_text}")
    
    def get_response_mode(
        self,
        confidence: RetrievalConfidence
    ) -> Tuple['ConfidenceLevel', str]:
        """
        Determine response mode based on tiered confidence.
        
        Returns:
            (ConfidenceLevel, reason_string)
        """
        from config import get_confidence_level, ConfidenceLevel
        
        level = get_confidence_level(confidence.overall_score)
        
        if level == ConfidenceLevel.HIGH:
            return (level, "High confidence - proceed with grounded response")
        
        elif level == ConfidenceLevel.MEDIUM:
            reasons = []
            if confidence.section_coverage < 0.8:
                reasons.append("some requested sections not found")
            if confidence.intent_matching < 0.7:
                reasons.append("partial intent match")
            reason = "; ".join(reasons) if reasons else "moderate confidence"
            return (level, f"Medium confidence: {reason}")
        
        elif level == ConfidenceLevel.LOW:
            reasons = []
            if confidence.section_coverage < 0.5:
                reasons.append("most requested sections missing")
            if confidence.legal_completeness < 0.5:
                reasons.append("required provisions not found")
            reason = "; ".join(reasons) if reasons else "low confidence"
            return (level, f"Low confidence - GPT-4 fallback: {reason}")
        
        else:  # VERY_LOW
            return (level, "Very low confidence - GPT-4 fallback with strong disclaimer")


if __name__ == "__main__":
    print("=" * 60)
    print("CONFIDENCE SCORER TEST")
    print("=" * 60)
    
    # Mock test
    from dataclasses import dataclass
    
    @dataclass
    class MockResult:
        score: float
        section_number: str
        text: str
    
    @dataclass
    class MockReformulated:
        extracted_sections: List[str]
    
    scorer = ConfidenceScorer()
    
    # Test 1: High confidence (section found)
    results = [
        MockResult(0.95, "IPC_302", "Section 302 of IPC deals with murder..."),
        MockResult(0.88, "IPC_302", "Murder is punishable under IPC 302..."),
        MockResult(0.75, "IPC_300", "Culpable homicide is defined..."),
    ]
    reformulated = MockReformulated(extracted_sections=["IPC_302"])
    
    confidence = scorer.compute_confidence(
        query="What is IPC 302?",
        reformulated_query=reformulated,
        results=results,
        query_type="legal_info"
    )
    
    print("\nTest 1: Section-specific query (IPC 302)")
    print(f"Overall Score: {confidence.overall_score:.2f} ({confidence.get_label()})")
    print(f"  - Section Coverage: {confidence.section_coverage:.2f}")
    print(f"  - Intent Matching: {confidence.intent_matching:.2f}")
    print(f"  - Source Redundancy: {confidence.source_redundancy:.2f}")
    print(f"  - Legal Completeness: {confidence.legal_completeness:.2f}")
    print(f"  - Avg Relevance: {confidence.avg_relevance:.2f}")
    
    use_fallback, reason = scorer.should_use_gpt4_fallback(confidence)
    print(f"\nUse GPT-4 Fallback: {use_fallback}")
    print(f"Reason: {reason}")
