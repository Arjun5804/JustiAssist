"""
JustiAssist Query Classifier Agent
Classifies user queries into Legal Information or Bail-Related categories using LLM and Heuristics.
"""

import re
import json
import asyncio
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass

from llm_provider import call_llm


class QueryType(Enum):
    """Types of legal queries"""
    LEGAL_INFO = "legal_information"
    BAIL_QUERY = "bail_related"
    DOCUMENT_QUERY = "document_query"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of query classification"""
    query_type: QueryType
    confidence: float
    detected_keywords: list
    reasoning: str


class QueryClassifier:
    """
    Classifies user queries to route them to appropriate processing pipelines.
    Uses LLM for semantic understanding, with keyword-based heuristics as a fast fallback.
    """
    
    # Bail-related keywords (fallback)
    BAIL_KEYWORDS = {
        'bail': 3.0, 'anticipatory': 4.0, 'regular bail': 4.0, 'surety': 2.5,
        'custody': 2.0, 'jail': 2.0, 'prison': 1.5, 'arrest': 2.0,
        'release': 2.0, 'crpc 436': 3.5, 'crpc 437': 3.5, 'crpc 438': 3.5,
        'section 437': 3.5, 'section 438': 3.5, 'section 439': 3.5
    }

    # Document-related keywords (fallback)
    DOCUMENT_KEYWORDS = {
        'document': 4.0, 'file': 3.0, 'uploaded': 4.0, 'pdf': 3.0, 'this fir': 2.0,
        'summarize': 3.0, 'extract': 2.0, 'what is this about': 3.0
    }
    
    def __init__(self, bail_threshold: float = 5.0):
        self.bail_threshold = bail_threshold
    
    async def classify(self, query: str) -> ClassificationResult:
        """
        Classify a user query using LLM (Semantic) -> Keywords (Fallback).
        This is an ASYNC method.
        """
        # 1. Try LLM Classification (Semantic)
        try:
            llm_result = await self._classify_with_llm(query)
            if llm_result:
                return llm_result
        except Exception as e:
            print(f"[QueryClassifier] LLM Classification failed: {e}. Falling back to keywords.")

        # 2. Fallback to Keyword Heuristics
        return self._classify_with_keywords(query)
    
    async def _classify_with_llm(self, query: str) -> Optional[ClassificationResult]:
        """Use LLM to interpret intent with improved prompt."""
        prompt = f"""You are a legal query classifier for an Indian legal AI system. Classify the query into exactly one category.

CATEGORIES:
1. BAIL_QUERY - User wants help with:
   - Getting someone out of jail/custody/lockup
   - Bail applications (regular, anticipatory, interim)
   - Release from police detention
   - Surety or bond requirements
   - Specific bail sections (CrPC 436, 437, 438, 439)
   - Examples: "my friend is in jail", "police took my brother", "how to get out of custody", "can I get bail for theft"

2. LEGAL_INFO - User wants information about:
   - What a law/section says (IPC, BNS, CrPC definitions)
   - Punishments for specific offenses
   - Legal procedures (FIR, chargesheet, trial)
   - Constitutional rights and articles
   - General legal knowledge
   - Examples: "what is IPC 302", "punishment for murder", "how to file FIR", "difference between IPC and BNS"

3. DOCUMENT_QUERY - User wants information specifically about an uploaded document:
   - Summarizing the document
   - Extracting names, dates, or details from the document
   - Explaining what the document means
   - Examples: "what is this document about", "summarize the uploaded FIR", "who is the accused in this document", "what sections are mentioned in the file"

IMPORTANT DISTINCTIONS:
- "Can I get bail?" → BAIL_QUERY (asking for help)
- "Is theft bailable?" → LEGAL_INFO (asking about law definition)
- "My son was arrested" → BAIL_QUERY (implies need for release)
- "What happens after arrest?" → LEGAL_INFO (asking about procedure)
- "Summarize this file" → DOCUMENT_QUERY

QUERY: "{query}"

Respond with JSON ONLY (no markdown):
{{"type": "BAIL_QUERY" or "LEGAL_INFO" or "DOCUMENT_QUERY", "confidence": 0.0-1.0, "reason": "brief explanation"}}"""
        
        # Use fast model if possible
        response = await call_llm(prompt)
        
        try:
            # Clean response
            clean_resp = response.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_resp)
            
            if data['type'] == 'BAIL_QUERY':
                q_type = QueryType.BAIL_QUERY
            elif data['type'] == 'DOCUMENT_QUERY':
                q_type = QueryType.DOCUMENT_QUERY
            else:
                q_type = QueryType.LEGAL_INFO
            
            return ClassificationResult(
                query_type=q_type,
                confidence=float(data.get('confidence', 0.9)),
                detected_keywords=[],  # LLM doesn't return keywords
                reasoning=f"[LLM] {data.get('reason', 'Semantic match')}"
            )
        except Exception as e:
            print(f"[QueryClassifier] Failed to parse LLM response: {response}")
            return None

    def _classify_with_keywords(self, query: str) -> ClassificationResult:
        """Original keyword-based logic as fallback."""
        query_lower = query.lower().strip()
        bail_score = 0.0
        doc_score = 0.0
        matched = []
        
        # Check Document Keywords first
        for kw, weight in self.DOCUMENT_KEYWORDS.items():
            if kw in query_lower:
                doc_score += weight
                matched.append(kw)
                
        if doc_score >= 3.0:
             return ClassificationResult(
                query_type=QueryType.DOCUMENT_QUERY,
                confidence=min(doc_score / 10.0, 1.0),
                detected_keywords=matched,
                reasoning=f"[Fallback] Document Keywords: {', '.join(matched)}"
            )
            
        matched.clear()
        
        for kw, weight in self.BAIL_KEYWORDS.items():
            if kw in query_lower:
                bail_score += weight
                matched.append(kw)
        
        if bail_score >= 3.0: # Lowered threshold for fallback
             return ClassificationResult(
                query_type=QueryType.BAIL_QUERY,
                confidence=min(bail_score / 10.0, 1.0),
                detected_keywords=matched,
                reasoning=f"[Fallback] Keywords: {', '.join(matched)}"
            )
            
        return ClassificationResult(
            query_type=QueryType.LEGAL_INFO,
            confidence=0.5,
            detected_keywords=[],
            reasoning="[Fallback] Defaulting to Legal Info"
        )
