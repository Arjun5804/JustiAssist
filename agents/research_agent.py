from agents.state import Agent, AgentState, AgentResult
from retrieval.pipeline import RetrievalPipeline
from retrieval.external import ExternalRetriever
from retrieval.evidence import EvidenceValidator
from confidence_scorer import ConfidenceScorer
from config import ConfidenceLevel, FALLBACK_LABELS
from agents.query_classifier import QueryType

class ResearchAgent(Agent):
    name: str = "ResearchAgent"

    def __init__(self, vector_store, reranker):
        self.retrieval_pipeline = RetrievalPipeline(vector_store, reranker)
        self.evidence_validator = EvidenceValidator()
        self.confidence_scorer = ConfidenceScorer()

    async def run(self, state: AgentState) -> AgentResult:
        state.agents_used.append(self.name)
        
        # 1. Local Retrieval
        evidence = self.retrieval_pipeline.run(
            query=state.query,
            enhanced_query=state.reformulated_query.enhanced_query if state.reformulated_query else state.query,
            query_type=state.query_type.value if hasattr(state.query_type, 'value') else state.query_type,
            extracted_sections=state.offense_sections,
            extracted_law_types=state.reformulated_query.extracted_law_types if state.reformulated_query else [],
            session_id=state.session_id
        )
        
        statutory_results = evidence.statutory_results
        bail_results = evidence.case_law_results
        
        total_retrieved = len(statutory_results) + len(bail_results)
        state.processing_info.setdefault("steps", []).append(f"✓ ResearcherAgent: {total_retrieved} results retrieved & reranked")

        # 2. Confidence Scoring (to determine if we need external fallback)
        use_fallback = False
        if state.query_type == QueryType.DOCUMENT_QUERY and state.session_documents:
            state.confidence_level = ConfidenceLevel.HIGH.value
            state.grounding_status = "pass"
        elif statutory_results:
            qtype_val = state.query_type.value if hasattr(state.query_type, 'value') else state.query_type
            retrieval_confidence = self.confidence_scorer.compute_confidence(
                query=state.query, 
                reformulated_query=state.reformulated_query,
                results=statutory_results, 
                query_type=qtype_val
            )
            state.confidence_score = round(retrieval_confidence.overall_score, 2)
            
            confidence_level, _ = self.confidence_scorer.get_response_mode(retrieval_confidence)
            state.confidence_level = confidence_level.value
            
            if confidence_level in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW):
                use_fallback = True
                state.grounding_status = "fail"
            elif confidence_level == ConfidenceLevel.MEDIUM:
                state.grounding_status = "partial"
            else:
                state.grounding_status = "pass"
                
            state.processing_info["confidence_breakdown"] = retrieval_confidence.to_dict()
        else:
            use_fallback = True
            state.grounding_status = "fail"

        # 3. External Retrieval Triggers
        query_lower = state.query.lower()
        is_new_law = any(x in query_lower for x in ["bns", "bnss", "bsa", "bharatiya"])
        is_election_or_special = any(x in query_lower for x in ["election", "voter", "conduct of election", "pmla", "ndps"])
        
        domain_mismatch = False
        if statutory_results:
            top_result_text = statutory_results[0].text.lower()
            if "election" in query_lower and "election" not in top_result_text:
                domain_mismatch = True
                
        trigger_web_search = use_fallback or is_new_law or is_election_or_special or domain_mismatch
        fetch_kanoon = (state.query_type == QueryType.BAIL_QUERY)
        fetch_news = trigger_web_search

        # 4. Fetch External Evidence
        if trigger_web_search or fetch_kanoon or fetch_news:
            state.agents_used.append("WebIntelAgent")
            try:
                external_results = await ExternalRetriever.retrieve(
                    query=state.query,
                    requested_sections=state.offense_sections[:2] if state.offense_sections else [],
                    trigger_web_search=trigger_web_search,
                    fetch_kanoon=fetch_kanoon,
                    fetch_news=fetch_news
                )
                if external_results:
                    if not hasattr(evidence, 'external_results'):
                        evidence.external_results = []
                    evidence.external_results.extend(external_results)
                    
                    # Populate UI metadata
                    for r in external_results:
                        if r.dataset_type == "external_web":
                            if "firecrawl_web" not in state.sources_used:
                                state.sources_used.append("firecrawl_web")
                        elif r.dataset_type == "indian_kanoon":
                            if "indian_kanoon" not in state.sources_used:
                                state.sources_used.append("indian_kanoon")
                            state.kanoon_cases.append({
                                "title": r.metadata.get("title", ""),
                                "citation": r.metadata.get("citation", ""),
                                "court": r.metadata.get("court", ""),
                                "date": r.provenance.source_date if r.provenance else "",
                                "url": r.metadata.get("url", ""),
                                "preview": r.text[:150]
                            })
                        elif r.dataset_type == "legal_news":
                            if "legal_news" not in state.sources_used:
                                state.sources_used.append("legal_news")
                            state.news_context.append({
                                "title": r.metadata.get("title", ""),
                                "source": r.metadata.get("source", ""),
                                "date": r.provenance.source_date if r.provenance else "",
                                "url": r.metadata.get("url", "")
                            })
                    state.processing_info["steps"].append(f"✓ ExternalRetriever: Retrieved {len(external_results)} external sources")
            except Exception as e:
                state.processing_info["steps"].append(f"⚠ ExternalRetriever Error: {e}")

        # 5. Evidence Validation (Hard Boundary)
        state.raw_evidence = evidence
        state.validated_evidence = self.evidence_validator.validate(evidence)
        state.has_retrieved = True
        state.has_validated = True
        
        return AgentResult(success=True, state=state)
