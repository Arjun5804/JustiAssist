from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
from retrieval.models import Claim

class VerificationVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_REFERENCE = "INVALID_REFERENCE"

@dataclass
class ClaimVerification:
    """Result of verifying a single claim."""
    claim_id: str
    verdict: VerificationVerdict
    evidence_ids: List[str] = field(default_factory=list)
    reason: Optional[str] = None

@dataclass
class GeneratedResponse:
    """Output from the GroundedGenerator."""
    answer: str
    claims: List[Claim] = field(default_factory=list)
    is_abstention: bool = False
    abstention_reason: Optional[str] = None
