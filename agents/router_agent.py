from agents.state import Agent, AgentState, AgentResult
from agents.query_classifier import QueryClassifier, QueryType
from agents.query_reformulator import QueryReformulator

class RouterAgent(Agent):
    name: str = "RouterAgent"

    def __init__(self):
        self.classifier = QueryClassifier()
        self.reformulator = QueryReformulator()

    async def run(self, state: AgentState) -> AgentResult:
        state.agents_used.append(self.name)
        
        # 1. Classification
        if state.mode == "auto":
            classification = await self.classifier.classify(state.query)
            state.query_type = classification.query_type
        elif state.mode == "bail":
            state.query_type = QueryType.BAIL_QUERY
        else:
            state.query_type = QueryType.LEGAL_INFO
            
        qtype_val = state.query_type.value if hasattr(state.query_type, 'value') else state.query_type
        state.processing_info.setdefault("steps", []).append(f"✓ ClassifierAgent: {qtype_val}")

        # 2. Reformulation
        reformulated = self.reformulator.reformulate(state.query)
        state.reformulated_query = reformulated
        state.offense_sections = reformulated.extracted_sections
        
        state.processing_info["steps"].append(
            f"✓ Query enhanced: {len(reformulated.search_terms)} terms, {len(state.offense_sections)} sections"
        )
        
        return AgentResult(success=True, state=state)
