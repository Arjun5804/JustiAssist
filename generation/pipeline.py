import logging
from typing import Optional, List
from retrieval.models import ValidatedEvidenceSet
from generation.models import GeneratedResponse, VerificationVerdict, ClaimVerification
from generation.generator import GroundedGenerator
from generation.verification import ClaimVerifier

logger = logging.getLogger(__name__)

class GroundedGenerationPipeline:
    """
    Orchestrates generation and verification loops.
    """
    
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.generator = GroundedGenerator()
        self.verifier = ClaimVerifier()
        
    def _format_feedback(self, verifications: List[ClaimVerification]) -> str:
        feedback = []
        for v in verifications:
            if v.verdict != VerificationVerdict.SUPPORTED:
                feedback.append(f"Claim ID {v.claim_id}: {v.verdict.value} - {v.reason}")
        return "\n".join(feedback)

    async def run(
        self, 
        query: str, 
        evidence: ValidatedEvidenceSet
    ) -> GeneratedResponse:
        
        # Fast exit if no evidence
        if not evidence.statutory_results and not evidence.case_law_results:
            return GeneratedResponse(
                answer="The available retrieved evidence does not sufficiently support a reliable answer.",
                claims=[],
                is_abstention=True,
                abstention_reason="Empty evidence set."
            )
            
        feedback = None
        for attempt in range(self.max_retries):
            # 1. Generate
            response = await self.generator.generate_response(query, evidence, feedback)
            
            if response.is_abstention:
                # If generator decided to abstain, we accept it
                return response
                
            # 2. Verify
            verifications = await self.verifier.verify_claims(response.claims, evidence)
            
            # 3. Check Policy
            unsupported = [v for v in verifications if v.verdict != VerificationVerdict.SUPPORTED]
            
            if not unsupported:
                # All claims supported
                return response
                
            if attempt < self.max_retries - 1:
                # Prepare feedback for retry
                feedback = self._format_feedback(unsupported)
                logger.info(f"Retrying generation. Feedback: {feedback}")
                continue
                
        # If we exhausted retries and still have unsupported claims
        return GeneratedResponse(
            answer="The available retrieved evidence does not sufficiently support a reliable answer.",
            claims=[],
            is_abstention=True,
            abstention_reason="Failed to produce fully supported claims after max retries."
        )
