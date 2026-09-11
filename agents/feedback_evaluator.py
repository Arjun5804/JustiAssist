"""
JustiAssist Feedback Evaluator Agent
Implements recursive feedback loop for grounding validation (LQ-RAG inspired)
"""

import re
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import httpx

from config import MAX_FEEDBACK_ITERATIONS


class EvaluationStatus(Enum):
    """Status of grounding evaluation"""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


@dataclass
class EvaluationResult:
    """Result of feedback evaluation"""
    status: EvaluationStatus
    issues: List[str]
    suggestions: List[str]
    grounding_score: float  # 0-1 how well grounded
    citation_count: int
    unsupported_claims: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "grounding_score": self.grounding_score,
            "citation_count": self.citation_count,
            "unsupported_claims": self.unsupported_claims
        }


class FeedbackEvaluator:
    """
    Feedback Evaluator Agent - Implements recursive grounding validation.
    
    Evaluation checks:
    1. Are all legal claims grounded in retrieved context?
    2. Are section numbers correct and cited?
    3. Is any hallucinated or unsupported law present?
    
    On FAIL: Triggers regeneration with stricter constraints.
    """
    
    # Known valid section patterns
    VALID_SECTION_PATTERNS = [
        r'IPC[\s_-]?\d+[A-Za-z]*',
        r'CrPC[\s_-]?\d+[A-Za-z]*',
        r'BNS[\s_-]?\d+[A-Za-z]*',
        r'Article[\s_-]?\d+[A-Za-z]*',
        r'Section[\s_]?\d+[A-Za-z]*',
    ]
    
    def __init__(self):
        self.max_iterations = MAX_FEEDBACK_ITERATIONS
    
    def evaluate(
        self,
        generated_response: str,
        retrieved_context: List[Dict[str, Any]],
        query: str
    ) -> EvaluationResult:
        """
        Evaluate if the generated response is properly grounded.
        
        Args:
            generated_response: The LLM-generated answer
            retrieved_context: The context chunks used for generation
            query: Original user query
            
        Returns:
            EvaluationResult with grounding assessment
        """
        issues = []
        suggestions = []
        unsupported_claims = []
        
        # Build context text for comparison
        context_text = " ".join([
            ctx.get('text', '') for ctx in retrieved_context
        ]).lower()
        
        context_sections = self._extract_sections_from_context(retrieved_context)
        
        # Check 1: Section citation validation
        cited_sections = self._extract_cited_sections(generated_response)
        invalid_sections = []
        
        for section in cited_sections:
            if not self._section_in_context(section, context_sections):
                invalid_sections.append(section)
        
        if invalid_sections:
            issues.append(f"Sections not found in context: {', '.join(invalid_sections)}")
            suggestions.append("Only cite sections that appear in the retrieved legal context")
        
        # Check 2: Legal claims grounding
        legal_claims = self._extract_legal_claims(generated_response)
        
        for claim in legal_claims:
            if not self._claim_grounded(claim, context_text):
                unsupported_claims.append(claim)
        
        if unsupported_claims:
            issues.append(f"Found {len(unsupported_claims)} potentially unsupported legal claims")
            suggestions.append("Ensure all legal statements are supported by retrieved context")
        
        # Check 3: Hallucination detection (fabricated laws)
        fabricated = self._detect_fabricated_sections(generated_response, context_sections)
        if fabricated:
            issues.append(f"Potentially fabricated section references: {', '.join(fabricated)}")
            suggestions.append("Remove references to non-existent legal sections")
            unsupported_claims.extend(fabricated)
        
        # Check 4: Citation density
        citation_count = len(cited_sections)
        if len(generated_response) > 500 and citation_count < 2:
            issues.append("Low citation density for detailed response")
            suggestions.append("Add more specific section citations to support claims")
        
        # Calculate grounding score
        grounding_score = self._calculate_grounding_score(
            total_claims=len(legal_claims),
            unsupported_count=len(unsupported_claims),
            invalid_sections=len(invalid_sections),
            citation_count=citation_count
        )
        
        # Determine status
        if grounding_score >= 0.8 and not invalid_sections:
            status = EvaluationStatus.PASS
        elif grounding_score >= 0.5:
            status = EvaluationStatus.PARTIAL
        else:
            status = EvaluationStatus.FAIL
        
        return EvaluationResult(
            status=status,
            issues=issues,
            suggestions=suggestions,
            grounding_score=grounding_score,
            citation_count=citation_count,
            unsupported_claims=unsupported_claims
        )
    
    def _extract_sections_from_context(
        self, 
        context: List[Dict[str, Any]]
    ) -> set:
        """Extract all section numbers from retrieved context"""
        sections = set()
        
        for ctx in context:
            # From metadata
            section = ctx.get('section_number', '')
            if section:
                sections.add(section.upper().replace(' ', '_'))
            
            # From text
            text = ctx.get('text', '')
            for pattern in self.VALID_SECTION_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    sections.add(match.upper().replace(' ', '_').replace('-', '_'))
        
        return sections
    
    def _extract_cited_sections(self, response: str) -> List[str]:
        """Extract section numbers cited in the response"""
        sections = []
        
        for pattern in self.VALID_SECTION_PATTERNS:
            matches = re.findall(pattern, response, re.IGNORECASE)
            sections.extend(matches)
        
        # Normalize
        return list(set([s.upper().replace(' ', '_').replace('-', '_') for s in sections]))
    
    def _section_in_context(self, section: str, context_sections: set) -> bool:
        """Check if a section was in the retrieved context"""
        normalized = section.upper().replace(' ', '_').replace('-', '_')
        
        # Direct match
        if normalized in context_sections:
            return True
        
        # Partial match (e.g., IPC_302 in IPC_302_CHUNK_1)
        for ctx_section in context_sections:
            if normalized in ctx_section or ctx_section in normalized:
                return True
        
        return False
    
    def _extract_legal_claims(self, response: str) -> List[str]:
        """Extract legal claims from response for grounding check"""
        claims = []
        
        # Patterns indicating legal claims
        claim_patterns = [
            r'(?:punish(?:able|ment)|sentence[d]?)\s+(?:with|by|for)[^.]+\.',
            r'(?:imprisonment|jail|fine)\s+(?:of|for|up to)[^.]+\.',
            r'(?:bailable|non-bailable)[^.]+\.',
            r'(?:under|as per|according to)\s+(?:section|ipc|crpc|bns)[^.]+\.',
            r'(?:maximum|minimum)\s+(?:punishment|penalty|sentence)[^.]+\.',
        ]
        
        for pattern in claim_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            claims.extend(matches)
        
        return claims[:10]  # Limit to prevent over-analysis
    
    def _claim_grounded(self, claim: str, context_text: str) -> bool:
        """Check if a claim is grounded in context"""
        # Extract key terms from claim
        claim_lower = claim.lower()
        
        # Check for key legal terms presence in context
        key_terms = re.findall(r'\b(?:imprisonment|fine|years|months|death|life|bailable)\b', claim_lower)
        
        if not key_terms:
            return True  # No specific legal terms to verify
        
        # Check if majority of terms appear in context
        matches = sum(1 for term in key_terms if term in context_text)
        return matches >= len(key_terms) * 0.5
    
    def _detect_fabricated_sections(
        self, 
        response: str, 
        context_sections: set
    ) -> List[str]:
        """Detect potentially fabricated section numbers"""
        fabricated = []
        
        # Find all section references in response
        all_sections = self._extract_cited_sections(response)
        
        for section in all_sections:
            # Check if section number seems valid but wasn't in context
            if not self._section_in_context(section, context_sections):
                # Check if it's a known invalid/non-existent section
                # (e.g., very high numbers, unusual formats)
                if self._is_suspicious_section(section):
                    fabricated.append(section)
        
        return fabricated
    
    def _is_suspicious_section(self, section: str) -> bool:
        """Check if a section number seems suspicious/fabricated"""
        # Extract numeric part
        numbers = re.findall(r'\d+', section)
        if not numbers:
            return False
        
        num = int(numbers[0])
        
        # IPC has ~500 sections, CrPC ~500, BNS ~350
        if 'IPC' in section.upper() and num > 600:
            return True
        if 'CRPC' in section.upper() and num > 500:
            return True
        if 'BNS' in section.upper() and num > 400:
            return True
        
        return False
    
    def _calculate_grounding_score(
        self,
        total_claims: int,
        unsupported_count: int,
        invalid_sections: int,
        citation_count: int
    ) -> float:
        """Calculate overall grounding score (0-1)"""
        if total_claims == 0:
            base_score = 0.7  # No claims to verify
        else:
            supported_ratio = 1 - (unsupported_count / total_claims)
            base_score = supported_ratio * 0.6
        
        # Penalty for invalid sections
        section_penalty = min(invalid_sections * 0.15, 0.3)
        
        # Bonus for citations
        citation_bonus = min(citation_count * 0.05, 0.2)
        
        score = base_score - section_penalty + citation_bonus
        return max(0.0, min(1.0, score + 0.2))  # Normalize
    
    def generate_improved_prompt(
        self,
        original_prompt: str,
        evaluation_result: EvaluationResult
    ) -> str:
        """
        Generate an improved prompt based on evaluation feedback.
        Used for regeneration attempts.
        """
        improvements = []
        
        if evaluation_result.unsupported_claims:
            improvements.append(
                "CRITICAL: Only state facts that are DIRECTLY supported by the retrieved context."
            )
        
        if evaluation_result.issues:
            improvements.append(
                f"ISSUES TO ADDRESS: {'; '.join(evaluation_result.issues)}"
            )
        
        if evaluation_result.suggestions:
            improvements.append(
                f"REQUIREMENTS: {'; '.join(evaluation_result.suggestions)}"
            )
        
        improvement_block = "\n".join(improvements)
        
        improved_prompt = f"""
{improvement_block}

GROUNDING CONSTRAINTS (MANDATORY):
1. ONLY cite sections that appear in the provided context
2. DO NOT fabricate or assume any legal provisions
3. If information is not available, explicitly state "Based on the available context, I cannot find..."
4. Every legal claim must be traceable to the retrieved documents

{original_prompt}
"""
        return improved_prompt


class FeedbackLoop:
    """
    Manages the recursive feedback loop for answer refinement.
    """
    
    def __init__(self, evaluator: FeedbackEvaluator, max_iterations: int = 3):
        self.evaluator = evaluator
        self.max_iterations = max_iterations
    
    def run(
        self,
        generate_fn,  # Function that generates response
        query: str,
        context: List[Dict[str, Any]],
        initial_prompt: str
    ) -> Tuple[str, EvaluationResult, int]:
        """
        Run the feedback loop until response passes or max iterations.
        
        Args:
            generate_fn: Function(prompt) -> response
            query: User query
            context: Retrieved context
            initial_prompt: Initial generation prompt
            
        Returns:
            Tuple of (final_response, evaluation_result, iterations_used)
        """
        current_prompt = initial_prompt
        best_response = ""
        best_score = 0.0
        iterations = 0
        
        for i in range(self.max_iterations):
            iterations = i + 1
            
            # Generate response
            response = generate_fn(current_prompt)
            
            # Evaluate
            evaluation = self.evaluator.evaluate(response, context, query)
            
            # Track best
            if evaluation.grounding_score > best_score:
                best_score = evaluation.grounding_score
                best_response = response
            
            # Check if passed
            if evaluation.status == EvaluationStatus.PASS:
                return response, evaluation, iterations
            
            # Generate improved prompt for next iteration
            current_prompt = self.evaluator.generate_improved_prompt(
                initial_prompt, 
                evaluation
            )
        
        # Return best response after max iterations
        final_eval = self.evaluator.evaluate(best_response, context, query)
        return best_response, final_eval, iterations


if __name__ == "__main__":
    # Test the feedback evaluator
    evaluator = FeedbackEvaluator()
    
    # Mock context
    mock_context = [
        {
            'section_number': 'IPC_302',
            'text': 'Section 302 IPC: Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.'
        },
        {
            'section_number': 'CrPC_437',
            'text': 'Section 437 CrPC: When any person accused of non-bailable offence is arrested or detained, he may be released on bail by a Magistrate.'
        }
    ]
    
    # Test response with good grounding
    good_response = """
Based on the retrieved legal provisions:

Under IPC Section 302, murder is punishable with death or imprisonment for life, along with fine. 
For bail in such cases, CrPC Section 437 governs the process where a Magistrate may grant bail 
for non-bailable offenses under certain conditions.
"""
    
    # Test response with hallucination
    bad_response = """
Under IPC Section 302, murder is punishable with death or imprisonment for life.
Additionally, IPC Section 999 provides for enhanced punishment in cases of organized crime.
The accused can apply for bail under CrPC Section 438.
"""
    
    print("="*60)
    print("FEEDBACK EVALUATION TEST")
    print("="*60)
    
    print("\n--- Good Response ---")
    result1 = evaluator.evaluate(good_response, mock_context, "murder bail")
    print(f"Status: {result1.status.value}")
    print(f"Grounding Score: {result1.grounding_score:.2f}")
    print(f"Issues: {result1.issues}")
    
    print("\n--- Bad Response (with hallucinations) ---")
    result2 = evaluator.evaluate(bad_response, mock_context, "murder bail")
    print(f"Status: {result2.status.value}")
    print(f"Grounding Score: {result2.grounding_score:.2f}")
    print(f"Issues: {result2.issues}")
    print(f"Unsupported Claims: {result2.unsupported_claims}")
