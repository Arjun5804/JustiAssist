from agents.state import Agent, AgentState, AgentResult
from generation.pipeline import GroundedGenerationPipeline

class ResponseAgent(Agent):
    name: str = "ResponseAgent"

    def __init__(self):
        # We reuse the existing GroundedGenerationPipeline which inherently
        # runs the retry loop using ClaimVerifier.
        self.pipeline = GroundedGenerationPipeline(max_retries=2)

    async def run(self, state: AgentState) -> AgentResult:
        state.agents_used.append("GroundedGenerationPipeline")
        
        # Hard invariant check: must have validated evidence
        if not state.validated_evidence:
            return AgentResult(success=False, state=state, error="Missing ValidatedEvidenceSet before generation.")
            
        gen_response = await self.pipeline.run(state.query, state.validated_evidence)
        state.generated_response = gen_response
        state.has_generated = True
        
        if gen_response.is_abstention:
            state.processing_info.setdefault("steps", []).append("✓ ResponseAgent: ABSTAINED")
        else:
            state.processing_info.setdefault("steps", []).append("✓ ResponseAgent: Generated grounded answer")
            
        return AgentResult(success=True, state=state)
