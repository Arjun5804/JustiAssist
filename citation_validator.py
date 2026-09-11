"""
JustiAssist Citation Validator
Pre-response validation to detect and handle hallucinated citations
"""

import re
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass


@dataclass
class CitationValidation:
    """Result of citation validation"""
    is_valid: bool
    cited_sections: List[str]
    valid_sections: List[str]
    invalid_sections: List[str]
    fabrication_score: float  # 0-1, higher = more fabricated


class CitationValidator:
    """
    Validates that all citations in a response exist in the provided context.
    Runs BEFORE response is returned to user.
    """
    
    # Patterns to extract section citations
    SECTION_PATTERNS = [
        r'(?:Section|Sec\.?)\s+(\d+[A-Za-z]?(?:\([^)]+\))?)',
        r'(?:IPC|CrPC|BNS|BNSS)\s+(\d+[A-Za-z]?)',
        r'(?:Article)\s+(\d+[A-Za-z]?(?:\([^)]+\))?)',
        r'धारा\s+(\d+[A-Za-z]?)',
    ]
    
    def extract_citations(self, text: str) -> Set[str]:
        """Extract all section citations from text"""
        citations = set()
        for pattern in self.SECTION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            citations.update(matches)
        return citations
    
    def validate(
        self,
        response: str,
        context_chunks: List[Dict],
        strict: bool = False
    ) -> CitationValidation:
        """
        Validate all citations in response against context.
        
        Args:
            response: LLM-generated response
            context_chunks: Retrieved context with section_number fields
            strict: If True, any invalid citation fails validation
            
        Returns:
            CitationValidation result
        """
        # Extract citations from response
        response_citations = self.extract_citations(response)
        
        # Build set of valid sections from context
        context_sections = set()
        for chunk in context_chunks:
            section = chunk.get('section_number', '')
            context_sections.add(section.upper())
            # Also add normalized versions
            context_sections.update(self.extract_citations(section))
            context_sections.update(self.extract_citations(chunk.get('text', '')))
        
        # Normalize all to uppercase for comparison
        context_sections = {s.upper() for s in context_sections if s}
        response_citations = {s.upper() for s in response_citations if s}
        
        # Validate each citation
        valid = []
        invalid = []
        
        for citation in response_citations:
            # Check if citation or normalized version exists in context
            if self._citation_in_context(citation, context_sections):
                valid.append(citation)
            else:
                invalid.append(citation)
        
        # Calculate fabrication score
        if response_citations:
            fabrication_score = len(invalid) / len(response_citations)
        else:
            fabrication_score = 0.0
        
        # Determine validity
        if strict:
            is_valid = len(invalid) == 0
        else:
            is_valid = fabrication_score < 0.3  # Allow up to 30% unknown
        
        return CitationValidation(
            is_valid=is_valid,
            cited_sections=list(response_citations),
            valid_sections=valid,
            invalid_sections=invalid,
            fabrication_score=fabrication_score
        )
    
    def _citation_in_context(self, citation: str, context_sections: Set[str]) -> bool:
        """Check if citation exists in context with fuzzy matching"""
        citation_clean = citation.replace('(', '_').replace(')', '').replace(' ', '')
        
        for ctx_section in context_sections:
            ctx_clean = ctx_section.replace('(', '_').replace(')', '').replace(' ', '')
            if citation_clean in ctx_clean or ctx_clean in citation_clean:
                return True
            # Check numeric part
            citation_num = re.search(r'\d+', citation_clean)
            ctx_num = re.search(r'\d+', ctx_clean)
            if citation_num and ctx_num and citation_num.group() == ctx_num.group():
                return True
        return False
    
    def sanitize_response(
        self,
        response: str,
        validation: CitationValidation
    ) -> str:
        """
        Previously appended warning text to the answer, but now returns
        the answer unchanged. Citation issues are communicated through
        structured data (processing_info) and the frontend's UI badges.
        """
        return response


# Global instance
citation_validator = CitationValidator()
