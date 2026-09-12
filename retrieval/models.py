from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

class AuthorityLevel(str, Enum):
    PRIMARY_OFFICIAL = "PRIMARY_OFFICIAL"
    TRUSTED_LEGAL = "TRUSTED_LEGAL"
    SECONDARY_LEGAL = "SECONDARY_LEGAL"
    NEWS = "NEWS"
    UNKNOWN = "UNKNOWN"

@dataclass
class Provenance:
    """Provenance metadata for an evidence item."""
    source_authority: AuthorityLevel = AuthorityLevel.UNKNOWN
    source_date: Optional[str] = None
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None

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
    provenance: Optional[Provenance] = None

@dataclass
class EvidenceSet:
    """Output of the RetrievalPipeline containing final retrieved chunks."""
    statutory_results: List[SearchResult] = field(default_factory=list)
    case_law_results: List[SearchResult] = field(default_factory=list)
    session_documents: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class ValidatedEvidenceSet:
    """Validated container/contract around existing evidence."""
    statutory_results: List[SearchResult] = field(default_factory=list)
    case_law_results: List[SearchResult] = field(default_factory=list)
    session_documents: List[Dict[str, Any]] = field(default_factory=list)
    validation_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Claim:
    """Represents a generated claim and the evidence chunks backing it."""
    claim_id: str
    text: str
    evidence_ids: List[str] = field(default_factory=list)
