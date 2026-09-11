"""
JustiAssist Retrieval Reranker
Two-stage retrieval with legal-specific ranking signals for maximum precision
"""

import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class SearchResult:
    """Unified search result structure"""
    chunk_id: str
    text: str
    score: float
    law_type: str
    section_number: str
    source_dataset: str
    dataset_type: str
    metadata: Dict[str, Any]


class LegalReranker:
    """
    Two-stage retrieval reranker optimized for legal documents.
    
    Reranking Signals:
    1. Statute Presence (40%) - Does chunk contain explicit legal sections?
    2. Section Match (30%) - Does it match user's requested sections?
    3. Legal Entity Density (15%) - Presence of court names, case citations
    4. Semantic Score (15%) - Original embedding similarity
    
    Process:
    - Retrieve top-k * 3 candidates from FAISS
    - Apply legal-specific reranking
    - Return top-k results
    """
    
    # Legal section markers (comprehensive patterns)
    SECTION_MARKERS = [
        r'section\s+\d+[a-z]*',
        r'sec\.\s*\d+[a-z]*',
        r'धारा\s+\d+[a-z]*',
        r'article\s+\d+[a-z]*',
        r'art\.\s*\d+[a-z]*',
        r'अनुच्छेद\s+\d+[a-z]*',
        r'ipc\s*\d+[a-z]*',
        r'crpc\s*\d+[a-z]*',
        r'bns\s*\d+[a-z]*',
    ]
    
    # Legal entities (courts, reports, etc.)
    LEGAL_ENTITIES = [
        r'supreme court',
        r'high court',
        r'district court',
        r'sessions court',
        r'\d{4}\s+scr',
        r'\d{4}\s+scc',
        r'\d{4}\s+air',
        r'\d{4}\s+\w+\s+\d+',  # Case citations like "2014 SC 1234"
        r'hon\'?ble court',
        r'learned judge',
    ]
    
    # Retrieval modes with different weight configurations
    WEIGHT_MODES = {
        'precision': {  # For section-specific queries
            'statute_presence': 0.40,
            'section_match': 0.40,
            'entity_density': 0.10,
            'semantic_score': 0.10,
        },
        'balanced': {  # Default mode
            'statute_presence': 0.40,
            'section_match': 0.30,
            'entity_density': 0.15,
            'semantic_score': 0.15,
        },
        'recall': {  # For concept-based queries
            'statute_presence': 0.25,
            'section_match': 0.15,
            'entity_density': 0.10,
            'semantic_score': 0.50,
        },
    }
    
    def __init__(self, mode: str = 'balanced'):
        """Initialize reranker with specified weight mode"""
        self.weights = self.WEIGHT_MODES.get(mode, self.WEIGHT_MODES['balanced'])
    
    def rerank(
        self,
        results: List[SearchResult],
        requested_sections: List[str],
        extracted_law_types: List[str] = None,
        top_k: int = 15,
        mode: str = None
    ) -> List[SearchResult]:
        """
        Rerank search results using legal-specific signals.
        
        Args:
            results: Initial search results from FAISS
            requested_sections: Sections extracted from user query (e.g., ["IPC_302"])
            top_k: Number of results to return
            mode: Override weight mode ('precision', 'balanced', 'recall')
            
        Returns:
            Reranked list of top-k results
        """
        if mode:
            weights = self.WEIGHT_MODES.get(mode, self.weights)
        else:
            weights = self.weights
        
        reranked = []
        
        for result in results:
            # 1. Statute Presence Score
            statute_score = self._compute_statute_presence(result.text)
            
            # 2. Section Match Score  
            match_score = self._compute_section_match(result, requested_sections)
            
            # 3. Law Type Match Score
            law_type_score = 1.0
            if extracted_law_types and result.law_type:
                if result.law_type.upper() in [lt.upper() for lt in extracted_law_types]:
                    law_type_score = 1.2  # Bonus
                else:
                    law_type_score = 0.5  # Penalty
                    
            # 4. Legal Entity Density Score
            entity_score = self._compute_entity_density(result.text)
            
            # 5. Semantic Score (from FAISS)
            semantic_score = result.score  # Already normalized 0-1
            
            # Compute weighted final score
            final_score = (
                weights['statute_presence'] * statute_score +
                weights['section_match'] * match_score +
                weights['entity_density'] * entity_score +
                weights['semantic_score'] * semantic_score
            ) * law_type_score
            
            # Create new result with updated score
            reranked_result = SearchResult(
                chunk_id=result.chunk_id,
                text=result.text,
                score=final_score,
                law_type=result.law_type,
                section_number=result.section_number,
                source_dataset=result.source_dataset,
                dataset_type=result.dataset_type,
                metadata={
                    **result.metadata,
                    'reranking_scores': {
                        'statute_presence': statute_score,
                        'section_match': match_score,
                        'law_type_multiplier': law_type_score,
                        'entity_density': entity_score,
                        'semantic_score': semantic_score,
                        'final_score': final_score,
                    }
                }
            )
            reranked.append(reranked_result)
        
        # Sort by final score (descending)
        reranked.sort(key=lambda x: x.score, reverse=True)
        
        return reranked[:top_k]
    
    def _compute_statute_presence(self, text: str) -> float:
        """
        Score based on presence of explicit legal sections.
        Returns: 0-1 score
        """
        text_lower = text.lower()
        matches = 0
        
        for pattern in self.SECTION_MARKERS:
            matches += len(re.findall(pattern, text_lower, re.IGNORECASE))
        
        # Normalize: more sections = higher score, cap at 1.0
        # Typical chunk has 1-3 sections, exceptional ones have 5+
        score = min(matches / 5.0, 1.0)
        return score
    
    def _compute_section_match(
        self,
        result: SearchResult,
        requested_sections: List[str]
    ) -> float:
        """
        Score based on matching user's requested sections.
        Returns: 0-1 score (1.0 if exact match, fractional if partial)
        """
        if not requested_sections:
            return 0.5  # Neutral score if no sections requested
        
        text_lower = result.text.lower()
        section_number_lower = result.section_number.lower()
        
        matches = 0
        for req_section in requested_sections:
            req_section_clean = req_section.lower().replace('_', ' ')
            
            # Exact match in section_number metadata
            if req_section_clean in section_number_lower:
                matches += 1
            # Match in text content
            elif req_section_clean in text_lower:
                matches += 0.5  # Partial credit
        
        # Normalize by number of requested sections
        score = matches / len(requested_sections)
        return min(score, 1.0)
    
    def _compute_entity_density(self, text: str) -> float:
        """
        Score based on legal entity density (courts, citations, etc.)
        Returns: 0-1 score
        """
        text_lower = text.lower()
        entity_count = 0
        
        for pattern in self.LEGAL_ENTITIES:
            entity_count += len(re.findall(pattern, text_lower, re.IGNORECASE))
        
        # Normalize by text length (entities per 1000 chars)
        text_length = max(len(text), 100)  # Avoid division by zero
        density = (entity_count / text_length) * 1000
        
        # Score: higher density = better, cap at 1.0
        # Typical case law has density ~5-10, statutes ~1-3
        score = min(density / 10.0, 1.0)
        return score
    
    def explain_reranking(self, result: SearchResult) -> str:
        """Generate human-readable explanation of reranking scores"""
        scores = result.metadata.get('reranking_scores', {})
        
        explanation = f"Reranking Breakdown:\n"
        explanation += f"  - Statute Presence: {scores.get('statute_presence', 0):.2f}\n"
        explanation += f"  - Section Match: {scores.get('section_match', 0):.2f}\n"
        explanation += f"  - Entity Density: {scores.get('entity_density', 0):.2f}\n"
        explanation += f"  - Semantic Score: {scores.get('semantic_score', 0):.2f}\n"
        explanation += f"  → Final Score: {scores.get('final_score', 0):.2f}\n"
        
        return explanation


if __name__ == "__main__":
    # Test the reranker
    print("=" * 60)
    print("LEGAL RERANKER TEST")
    print("=" * 60)
    
    # Mock search results
    mock_results = [
        SearchResult(
            chunk_id="1",
            text="Section 302 of IPC deals with punishment for murder. The Supreme Court in 2014 held that...",
            score=0.85,
            law_type="IPC",
            section_number="302",
            source_dataset="ipc_sections.csv",
            dataset_type="statutory",
            metadata={}
        ),
        SearchResult(
            chunk_id="2",
            text="General information about criminal law without specific sections mentioned.",
            score=0.90,  # Higher semantic but no legal markers
            law_type="Unknown",
            section_number="N/A",
            source_dataset="generic.csv",
            dataset_type="unknown",
            metadata={}
        ),
        SearchResult(
            chunk_id="3",
            text="IPC 302 - Murder - whoever commits murder shall be punished with death or life imprisonment.",
            score=0.75,
            law_type="IPC",
            section_number="IPC_302",
            source_dataset="ipc_sections.csv",
            dataset_type="statutory",
            metadata={}
        ),
    ]
    
    reranker = LegalReranker(mode='precision')
    requested_sections = ["IPC_302"]
    
    reranked = reranker.rerank(mock_results, requested_sections, top_k=3)
    
    print("\nReranked Results:")
    for i, result in enumerate(reranked, 1):
        print(f"\n{i}. {result.section_number} (Final Score: {result.score:.3f})")
        print(f"   Text: {result.text[:100]}...")
        print(f"   {reranker.explain_reranking(result)}")
