from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Protocol
from agents.query_classifier import QueryType
from agents.query_reformulator import ReformulatedQuery
from retrieval.models import EvidenceSet, ValidatedEvidenceSet
from generation.models import GeneratedResponse

@dataclass
class AgentState:
    # Inputs
    query: str
    mode: str = "auto"
    chat_history: str = ""
    session_documents: List[Dict[str, Any]] = field(default_factory=list)
    custody_days: Optional[int] = None
    offense_sections: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    
    # Classification / Reformulation
    query_type: Optional[QueryType] = None
    reformulated_query: Optional[ReformulatedQuery] = None
    
    # Evidence
    raw_evidence: Optional[EvidenceSet] = None
    validated_evidence: Optional[ValidatedEvidenceSet] = None
    
    # Analysis
    confidence_score: float = 0.0
    confidence_level: Optional[str] = None
    grounding_status: str = "unknown"
    bail_assessment: Optional[Dict[str, Any]] = None
    
    # Generation & Verification
    generated_response: Optional[GeneratedResponse] = None
    final_answer: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    is_abstention: bool = False
    
    # Metadata for UI
    processing_info: Dict[str, Any] = field(default_factory=dict)
    kanoon_cases: List[Dict[str, Any]] = field(default_factory=list)
    news_context: List[Dict[str, Any]] = field(default_factory=list)
    sources_used: List[str] = field(default_factory=list)
    agents_used: List[str] = field(default_factory=list)
    
    # Lifecycle tracker
    has_retrieved: bool = False
    has_validated: bool = False
    has_generated: bool = False
    has_verified: bool = False

@dataclass
class AgentResult:
    success: bool
    state: AgentState
    error: Optional[str] = None

class Agent(Protocol):
    name: str

    async def run(self, state: AgentState) -> AgentResult:
        ...
