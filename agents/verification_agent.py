from agents.state import Agent, AgentState, AgentResult
from retrieval.models import SearchResult
from generation.models import VerificationVerdict

class VerificationAgent(Agent):
    name: str = "VerificationAgent"

    async def run(self, state: AgentState) -> AgentResult:
        state.agents_used.append(self.name)
        
        # Hard invariant: must have generated response
        if not state.has_generated or not state.generated_response:
            return AgentResult(success=False, state=state, error="VerificationAgent executed without a GeneratedResponse.")
            
        gen_response = state.generated_response
        
        # Hard invariant: check that claims are actually verified and not bypassed
        # (This acts as the final boundary gate)
        
        if gen_response.is_abstention:
            state.final_answer = gen_response.answer
            state.citations = []
            state.confidence_score = 0.0
            state.grounding_status = "fail"
            state.has_verified = True
            state.processing_info.setdefault("steps", []).append("✓ VerificationAgent: Confirmed abstention")
            return AgentResult(success=True, state=state)
            
        # Hard invariant: check that claims were actually subjected to semantic verification
        if len(gen_response.claims) > 0 and not gen_response.verifications:
            state.final_answer = "The available retrieved evidence does not sufficiently support a reliable answer."
            state.citations = []
            state.confidence_score = 0.0
            state.grounding_status = "fail"
            state.has_verified = True
            state.processing_info.setdefault("steps", []).append("⚠ VerificationAgent: Rejected response due to missing verification results")
            return AgentResult(success=True, state=state)
            
        # Hard invariant: check that no unsupported claims leaked
        unsupported = [v for v in gen_response.verifications if v.verdict != VerificationVerdict.SUPPORTED]
        if unsupported:
            state.final_answer = "The available retrieved evidence does not sufficiently support a reliable answer."
            state.citations = []
            state.confidence_score = 0.0
            state.grounding_status = "fail"
            state.has_verified = True
            state.processing_info.setdefault("steps", []).append("⚠ VerificationAgent: Rejected response due to unsupported claims leaking past generation")
            return AgentResult(success=True, state=state)
            
        # Format citations from canonical evidence mapping
        referenced_ids = set()
        for c in gen_response.claims:
            referenced_ids.update(c.evidence_ids)
                
        all_results = state.validated_evidence.statutory_results + state.validated_evidence.case_law_results
        if hasattr(state.validated_evidence, 'external_results'):
            all_results.extend(state.validated_evidence.external_results)
            
        for doc in state.validated_evidence.session_documents:
            all_results.append(SearchResult(
                chunk_id=doc.get("chunk_id", "unknown"),
                text=doc.get("text", ""),
                score=doc.get("score", 0.0),
                law_type="document",
                section_number="N/A",
                source_dataset="session_documents",
                dataset_type="document",
                metadata={"filename": doc.get("filename", "")}
            ))
            
        used_results = [r for r in all_results if r.chunk_id in referenced_ids]
        
        # Ensure we don't have a non-abstained response with zero citations
        if not used_results and len(gen_response.claims) > 0:
            # Fallback to abstention if claims are ungrounded
            state.final_answer = "The available retrieved evidence does not sufficiently support a reliable answer."
            state.citations = []
            state.confidence_score = 0.0
            state.grounding_status = "fail"
            state.has_verified = True
            state.processing_info.setdefault("steps", []).append("⚠ VerificationAgent: Rejected response due to missing citations")
            return AgentResult(success=True, state=state)
        
        # Format citations
        citations = []
        for result in used_results:
            citations.append({
                "section": result.section_number,
                "law_type": result.law_type,
                "text_preview": result.text[:200] + "..." if len(result.text) > 200 else result.text,
                "source": result.source_dataset,
                "relevance_score": round(result.score, 3)
            })
            
        state.final_answer = gen_response.answer
        state.citations = citations
        state.has_verified = True
        state.processing_info.setdefault("steps", []).append("✓ VerificationAgent: Final verification gate passed and citations built")
        
        return AgentResult(success=True, state=state)
