import json
from typing import List, Dict, Any, Optional
from retrieval.models import ValidatedEvidenceSet, Claim, SearchResult
from generation.models import ClaimVerification, VerificationVerdict
from llm_provider import call_llm
from config import AnswerMode
import logging

logger = logging.getLogger(__name__)

class ClaimVerifier:
    """
    Deterministically and semantically verifies a claim against evidence.
    """

    def __init__(self):
        pass
        
    def _get_evidence_mapping(self, evidence: ValidatedEvidenceSet) -> Dict[str, SearchResult]:
        mapping = {}
        for item in evidence.statutory_results:
            mapping[item.chunk_id] = item
        for item in evidence.case_law_results:
            mapping[item.chunk_id] = item
        return mapping

    async def verify_claims(
        self, 
        claims: List[Claim], 
        evidence: ValidatedEvidenceSet
    ) -> List[ClaimVerification]:
        
        mapping = self._get_evidence_mapping(evidence)
        results = []
        
        for claim in claims:
            result = await self.verify_claim(claim, mapping)
            results.append(result)
            
        return results

    async def verify_claim(
        self, 
        claim: Claim, 
        evidence_mapping: Dict[str, SearchResult]
    ) -> ClaimVerification:
        """
        Verifies a single claim.
        1. Checks for missing or empty text.
        2. Checks for missing evidence IDs (completeness).
        3. Checks if evidence IDs exist in mapping (reference validity).
        4. Performs semantic verification using LLM.
        """
        if not claim.text or not claim.text.strip():
            return ClaimVerification(
                claim_id=claim.claim_id,
                verdict=VerificationVerdict.UNSUPPORTED,
                reason="Claim text is empty."
            )
            
        if not claim.evidence_ids:
            return ClaimVerification(
                claim_id=claim.claim_id,
                verdict=VerificationVerdict.UNSUPPORTED,
                reason="Substantive claim missing evidence citations."
            )
            
        referenced_evidence = []
        for eid in claim.evidence_ids:
            if eid not in evidence_mapping:
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    verdict=VerificationVerdict.INVALID_REFERENCE,
                    evidence_ids=claim.evidence_ids,
                    reason=f"Evidence ID '{eid}' is not in the provided ValidatedEvidenceSet."
                )
            referenced_evidence.append(evidence_mapping[eid])
            
        # Semantic check using isolated LLM
        return await self._semantic_verify(claim, referenced_evidence)

    async def _semantic_verify(
        self, 
        claim: Claim, 
        referenced_evidence: List[SearchResult]
    ) -> ClaimVerification:
        
        evidence_text = "\n".join([f"[{e.chunk_id}] {e.text}" for e in referenced_evidence])
        
        prompt = f"""You are an exact and strict verifier.
Your ONLY job is to determine if the supplied EVIDENCE fully supports the CLAIM.

CLAIM: "{claim.text}"

EVIDENCE:
{evidence_text}

Does the evidence fully support the claim, partially support it, or not support it at all?
You must output a JSON object with exactly this format:
{{
    "verdict": "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED",
    "reason": "Brief explanation of why."
}}

Do NOT use outside knowledge. If the evidence does not state the claim, it is UNSUPPORTED.
If the claim goes beyond what is in the evidence, it is PARTIALLY_SUPPORTED or UNSUPPORTED.
"""
        
        try:
            # We use fallback mode to avoid strict grounded mode prompt which might conflict 
            # with our custom prompt instructions. But we still want no hallucination.
            raw_response = await call_llm(prompt, temperature=0.1)
            
            # Extract JSON
            start_idx = raw_response.find("{")
            end_idx = raw_response.rfind("}")
            
            if start_idx != -1 and end_idx != -1:
                json_str = raw_response[start_idx:end_idx+1]
                data = json.loads(json_str)
                verdict_str = data.get("verdict", "UNSUPPORTED")
                reason = data.get("reason", "")
                
                try:
                    verdict = VerificationVerdict(verdict_str)
                except ValueError:
                    verdict = VerificationVerdict.UNSUPPORTED
                    
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    verdict=verdict,
                    evidence_ids=claim.evidence_ids,
                    reason=reason
                )
            else:
                logger.error("Semantic verifier failed to return JSON.")
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    verdict=VerificationVerdict.UNSUPPORTED,
                    evidence_ids=claim.evidence_ids,
                    reason="Semantic verification failed to parse output."
                )
                
        except Exception as e:
            logger.error(f"Semantic verifier exception: {e}")
            return ClaimVerification(
                claim_id=claim.claim_id,
                verdict=VerificationVerdict.UNSUPPORTED,
                evidence_ids=claim.evidence_ids,
                reason=f"Verifier error: {str(e)}"
            )
