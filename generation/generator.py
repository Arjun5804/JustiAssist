import json
import logging
from typing import List, Dict, Any, Optional
from retrieval.models import ValidatedEvidenceSet, Claim
from generation.models import GeneratedResponse
from llm_provider import call_llm
from config import AnswerMode

logger = logging.getLogger(__name__)

class GroundedGenerator:
    """
    Generator responsible purely for producing one structured GeneratedResponse
    from a ValidatedEvidenceSet.
    Does NOT contain verification or revision loops.
    """

    def __init__(self):
        pass

    def _build_evidence_text(self, evidence: ValidatedEvidenceSet) -> str:
        text_parts = []
        
        for item in evidence.statutory_results:
            text_parts.append(f"[Evidence ID: {item.chunk_id}]\nSection: {item.section_number}\nSource: {item.source_dataset}\n{item.text}\n")
            
        for item in evidence.case_law_results:
            text_parts.append(f"[Evidence ID: {item.chunk_id}]\nSection: {item.section_number}\nSource: {item.source_dataset}\n{item.text}\n")
            
        return "\n".join(text_parts)

    def _extract_json(self, text: str) -> str:
        # Simple extraction to handle markdown JSON blocks
        start_idx = text.find("```json")
        if start_idx != -1:
            end_idx = text.find("```", start_idx + 7)
            if end_idx != -1:
                return text[start_idx + 7:end_idx].strip()
        
        start_idx = text.find("```")
        if start_idx != -1:
            end_idx = text.find("```", start_idx + 3)
            if end_idx != -1:
                return text[start_idx + 3:end_idx].strip()
                
        return text.strip()

    async def generate_response(
        self, 
        query: str, 
        evidence: ValidatedEvidenceSet,
        feedback: Optional[str] = None
    ) -> GeneratedResponse:
        """
        Generates a structured response based ONLY on the provided evidence.
        """
        evidence_text = self._build_evidence_text(evidence)
        
        prompt = f"""You are JustiAssist, an AI legal assistant.
You must answer the user's query based ONLY on the provided Evidence.

USER QUERY: {query}

EVIDENCE CONTEXT:
{evidence_text}

INSTRUCTIONS:
1. Provide a comprehensive legal answer based on the evidence.
2. Break down the factual and legal assertions in your answer into a list of Claims.
3. For each Claim, you MUST provide an array of `evidence_ids` corresponding to the exact Evidence ID in the context that supports it.
4. Do NOT invent or hallucinate evidence_ids, section numbers, or facts.
5. If the evidence is completely insufficient to answer the query, provide a general abstention answer and leave claims empty.
"""
        
        if feedback:
            prompt += f"\nFEEDBACK FROM PREVIOUS ATTEMPT:\n{feedback}\nPlease revise your answer to fix these issues. Ensure unsupported claims are removed or revised."
            
        prompt += """
You must respond with a strict JSON object matching the following structure:
{
    "answer": "Your detailed legal answer here...",
    "claims": [
        {
            "claim_id": "claim_1",
            "text": "Specific legal or factual assertion extracted from the answer.",
            "evidence_ids": ["chunk_123", "chunk_456"]
        }
    ]
}

Return ONLY valid JSON.
"""
        try:
            raw_response = await call_llm(prompt, answer_mode=AnswerMode.GROUNDED)
            json_text = self._extract_json(raw_response)
            data = json.loads(json_text)
            
            claims = []
            for c in data.get("claims", []):
                claims.append(Claim(
                    claim_id=c.get("claim_id", ""),
                    text=c.get("text", ""),
                    evidence_ids=c.get("evidence_ids", [])
                ))
                
            return GeneratedResponse(
                answer=data.get("answer", ""),
                claims=claims
            )
        except Exception as e:
            logger.error(f"Failed to generate structured response: {e}")
            return GeneratedResponse(
                answer="The system could not generate a valid supported response.",
                claims=[],
                is_abstention=True,
                abstention_reason=f"Generation failure: {str(e)}"
            )
