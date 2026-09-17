"""
JustiAssist Audit Logger
Structured logging for production observability
"""

import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class RetrievalEvent:
    """Logged when retrieval completes"""
    event_type: str = "retrieval"
    query_id: str = ""
    timestamp: str = ""
    query_hash: str = ""
    reformulated_query_hash: str = ""
    search_type: str = ""  # "hybrid" or "semantic"
    num_results: int = 0
    top_5_sections: List[str] = field(default_factory=list)
    top_5_scores: List[float] = field(default_factory=list)
    confidence_score: float = 0.0
    confidence_level: str = ""


@dataclass
class GenerationEvent:
    """Logged when generation completes"""
    event_type: str = "generation"
    query_id: str = ""
    timestamp: str = ""
    grounding_mode: str = ""
    response_length: int = 0
    citations_count: int = 0
    citations_valid: int = 0
    citations_invalid: int = 0
    fabrication_score: float = 0.0
    llm_model: str = ""
    latency_ms: int = 0


class AuditLogger:
    """Structured audit logger for JustiAssist"""
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Set up file handler
        self.logger = logging.getLogger("justiassist.audit")
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            handler = logging.FileHandler(
                self.log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
    
    def _log(self, event: Any):
        """Log event as JSON line"""
        self.logger.info(json.dumps(asdict(event), default=str))
    
    def log_retrieval(
        self,
        query_id: str,
        query_text: str,
        reformulated_query: str,
        results: List[Any],
        confidence_score: float,
        confidence_level: str,
        search_type: str = "hybrid"
    ):
        """Log retrieval event securely hashing PII"""
        
        q_hash = hashlib.sha256(query_text.encode('utf-8')).hexdigest() if query_text else ""
        r_hash = hashlib.sha256(reformulated_query.encode('utf-8')).hexdigest() if reformulated_query else ""
        
        event = RetrievalEvent(
            query_id=query_id,
            timestamp=datetime.utcnow().isoformat(),
            query_hash=q_hash,
            reformulated_query_hash=r_hash,
            search_type=search_type,
            num_results=len(results),
            top_5_sections=[getattr(r, 'section_number', '') for r in results[:5]],
            top_5_scores=[round(getattr(r, 'score', 0), 3) for r in results[:5]],
            confidence_score=round(confidence_score, 3),
            confidence_level=confidence_level,
        )
        self._log(event)
    
    def log_generation(
        self,
        query_id: str,
        grounding_mode: str,
        response: str,
        citations_valid: int,
        citations_invalid: int,
        fabrication_score: float,
        llm_model: str,
        latency_ms: int
    ):
        """Log generation event"""
        event = GenerationEvent(
            query_id=query_id,
            timestamp=datetime.utcnow().isoformat(),
            grounding_mode=grounding_mode,
            response_length=len(response),
            citations_count=citations_valid + citations_invalid,
            citations_valid=citations_valid,
            citations_invalid=citations_invalid,
            fabrication_score=round(fabrication_score, 3),
            llm_model=llm_model,
            latency_ms=latency_ms
        )
        self._log(event)


# Global instance
audit_logger = AuditLogger()
