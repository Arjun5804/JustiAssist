from agents.state import Agent, AgentState, AgentResult
from agents.bail_evaluator import BailEvaluator
from agents.query_classifier import QueryType

class AnalysisAgent(Agent):
    name: str = "AnalysisAgent"

    def __init__(self):
        self.bail_evaluator = BailEvaluator()

    async def run(self, state: AgentState) -> AgentResult:
        if state.query_type == QueryType.BAIL_QUERY:
            state.agents_used.append("BailAnalystAgent")
            
            if state.session_documents:
                # Document-specific bail assessment
                state.bail_assessment = {
                    "bail_likelihood": "Document Analysis",
                    "legal_reasoning": {
                        "bailable_status": "See document", 
                        "max_punishment": "See document", 
                        "severity_score": 0, 
                        "applicable_crpc": ["Based on uploaded document"]
                    },
                    "explanation": "Analysis based on uploaded court document/FIR."
                }
            else:
                # Standard bail assessment based on validated evidence
                all_results = state.validated_evidence.statutory_results + state.validated_evidence.case_law_results
                if hasattr(state.validated_evidence, 'external_results'):
                    all_results.extend(state.validated_evidence.external_results)
                    
                # Convert SearchResult to dict as expected by BailEvaluator
                statutory_context = [
                    {
                        "law_type": r.law_type,
                        "section_number": r.section_number,
                        "text": r.text
                    } for r in state.validated_evidence.statutory_results
                ]
                
                # We need case law for precedents
                bail_precedents = [
                    {
                        "text": r.text,
                        "score": r.score,
                        "metadata": r.metadata
                    } for r in state.validated_evidence.case_law_results
                ]
                
                bail_eval = await self.bail_evaluator.evaluate(
                    query=state.query,
                    statutory_context=statutory_context,
                    bail_precedents=bail_precedents,
                    custody_duration_days=state.custody_days,
                    offense_sections=state.offense_sections
                )
                
                state.bail_assessment = bail_eval.to_dict()
                
            state.processing_info.setdefault("steps", []).append("✓ AnalysisAgent: Computed bail likelihood")
            
        return AgentResult(success=True, state=state)
