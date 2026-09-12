from dataclasses import dataclass, field
from typing import Dict, Any, List

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

@dataclass
class EvidenceSet:
    """Output of the RetrievalPipeline containing final retrieved chunks."""
    statutory_results: List[SearchResult] = field(default_factory=list)
    case_law_results: List[SearchResult] = field(default_factory=list)
    session_documents: List[Dict[str, Any]] = field(default_factory=list)
