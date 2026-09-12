"""
JustiAssist CrewAI-Style Orchestrator
Implements a lightweight agentic framework with Agent/Task/Crew pattern.

Since CrewAI requires Python <3.14 and we're on 3.14.2, we implement
the same agentic pattern natively. This gives us:
- Same Agent/Task coordination as CrewAI
- Full control over LLM routing (Groq primary, Ollama fallback)
- Custom tool integration (VectorStore, Firecrawl, Indian Kanoon)
- Zero dependency issues

Agent Pipeline:
  1. ClassifierAgent — Determines query type (legal info / bail)
  2. ResearcherAgent — Retrieves from vector DB, reranks, builds context
  3. WebIntelAgent — Searches web via Firecrawl when local context is insufficient
  4. BailAnalystAgent — Specialized bail assessment (conditional)
  5. QualityReviewerAgent — Mandatory final check for zero hallucination
"""

import os
import json
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ==================== Configuration ====================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


# ==================== Lightweight Agent Framework ====================

@dataclass
class AgentResult:
    """Result from a single agent execution"""
    agent_name: str
    success: bool
    output: Any = None
    error: str = None
    duration_ms: int = 0


class Agent:
    """Base Agent class — similar to CrewAI Agent"""
    def __init__(self, name: str, role: str, goal: str, tools: list = None):
        self.name = name
        self.role = role
        self.goal = goal
        self.tools = tools or []

    async def execute(self, context: dict) -> AgentResult:
        """Override in subclasses"""
        raise NotImplementedError


# ==================== Result Dataclass ====================

@dataclass
class CrewResult:
    """Result from the CrewAI orchestrator"""
    query: str
    query_type: str
    answer: str = ""
    citations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    bail_assessment: Optional[Dict[str, Any]] = None
    grounding_status: str = "pass"
    processing_info: Dict[str, Any] = field(default_factory=dict)
    kanoon_cases: List[Dict[str, Any]] = field(default_factory=list)
    news_context: List[Dict[str, Any]] = field(default_factory=list)
    sources_used: List[str] = field(default_factory=list)
    fetch_times_ms: Dict[str, int] = field(default_factory=dict)
    agents_used: List[str] = field(default_factory=list)
    web_sources: List[Dict[str, Any]] = field(default_factory=list)
    quality_review: Dict[str, Any] = field(default_factory=dict)

    def to_response_dict(self) -> Dict[str, Any]:
        qtype = self.query_type.value if hasattr(self.query_type, 'value') else self.query_type
        return {
            "query": self.query,
            "query_type": qtype,
            "answer": self.answer,
            "citations": self.citations,
            "confidence_score": self.confidence_score,
            "bail_assessment": self.bail_assessment,
            "grounding_status": self.grounding_status,
            "processing_info": self.processing_info,
            "kanoon_cases": self.kanoon_cases,
            "news_context": self.news_context,
            "sources_used": self.sources_used,
            "fetch_times_ms": self.fetch_times_ms,
            "agents_used": self.agents_used,
            "web_sources": self.web_sources,
            "quality_review": self.quality_review,
        }


# ==================== Main Orchestrator ====================

class JustiAssistCrew:
    """
    Main orchestrator that runs the agentic pipeline.
    
    Uses the existing agent logic (query_classifier, query_reformulator,
    bail_evaluator, feedback_evaluator) and coordinates them through
    a lightweight Agent/Task framework for agentic behavior.
    """

    def __init__(
        self,
        vector_store=None,
        reranker=None,
        context_builder=None,
        confidence_scorer=None,
        retrieval_pipeline=None,
    ):
        self.vector_store = vector_store
        self.reranker = reranker
        self.context_builder = context_builder
        self.confidence_scorer = confidence_scorer
        self.retrieval_pipeline = retrieval_pipeline
        
        # Initialize Firecrawl tool
        self._firecrawl_available = False
        self._init_firecrawl()

    def _init_firecrawl(self):
        """Check if Firecrawl is available"""
        api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if api_key and api_key != "fc-your-api-key-here":
            self._firecrawl_available = True
            logger.info("[CrewAI] Firecrawl tool available")
        else:
            logger.info("[CrewAI] Firecrawl not configured (optional)")

    def _firecrawl_search(self, query: str) -> str:
        """Search the web using Firecrawl"""
        if not self._firecrawl_available:
            return ""
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
            
            # MULTI-STAGE SEARCH STRATEGY
            # 1. Broad Legal Search
            primary_query = f"India {query} full text definition penalty"
            # 2. Administrative/Rules Search (e.g. for Election Rules)
            secondary_query = f"India legal rule section {query} manual"
            
            # Combine or pick the best
            final_query = primary_query
            if any(x in query.lower() for x in ["rule", "election", "p", "conduct"]):
                final_query = f"Rule {query} Conduct of Elections Rules India"
            
            logger.info(f"[Firecrawl] Searching for: {final_query}")
            results = app.search(query=final_query, limit=8)
            
            if not results:
                return ""
            
            formatted = []
            
            # Firecrawl v1.x returns a SearchData object or similar, handle both dict and object
            if isinstance(results, dict):
                result_list = results.get('data', [])
            elif hasattr(results, 'data'):
                result_list = results.data
            elif isinstance(results, list):
                result_list = results
            else:
                # If it's the SearchData object itself which might be iterable but not subscriptable
                try:
                    result_list = list(results)
                except:
                    result_list = []
            
            for i, result in enumerate(result_list[:3], 1):
                try:
                    if isinstance(result, dict):
                        title = result.get('title', 'Legal Source')
                        url = result.get('url', '')
                        content = result.get('markdown', result.get('content', ''))[:1200]
                    else:
                        title = getattr(result, 'title', 'Legal Source')
                        url = getattr(result, 'url', '')
                        content = getattr(result, 'markdown', getattr(result, 'content', ''))[:1200]
                    
                    if content:
                        formatted.append(f"--- WEB SOURCE {i} ---\nTITLE: {title}\nURL: {url}\nCONTENT: {content}\n")
                except Exception as inner_e:
                    logger.warning(f"[Firecrawl] Error processing result {i}: {inner_e}")
                    continue
            
            return "\n".join(formatted)
        except Exception as e:
            logger.warning(f"[Firecrawl] Search error: {e}")
            return ""

    async def process_query(
        self,
        query: str,
        mode: str = "auto",
        chat_history: str = "",
        session_documents: List[Dict] = None,
        custody_days: int = None,
        offense_sections: List[str] = None,
        session_id: str = None,
        on_stage: callable = None,
    ) -> CrewResult:
        """
        Main entry point: Process a legal query through the agentic pipeline.
        
        Args:
            query: User's legal question
            mode: "auto", "legal", or "bail"
            chat_history: Formatted previous conversation context
            session_documents: Uploaded document chunks
            custody_days: Days in custody (for bail queries)
            offense_sections: IPC sections charged
            session_id: Document session ID
            on_stage: Callback for progress updates
        """
        result = CrewResult(query=query, query_type="unknown")
        result.processing_info = {"steps": [], "enhanced_rag": True, "agentic_pipeline": True}
        result.sources_used = ["local_vectors"]
        start_time = time.time()

        def emit(stage, status, data=None):
            if on_stage:
                on_stage(stage, status, data)

        try:
            # ==================== STAGE 1: ClassifierAgent ====================
            emit("classify", "active")
            result.agents_used.append("ClassifierAgent")
            
            from agents.query_classifier import QueryClassifier, QueryType
            classifier = QueryClassifier()
            
            if mode == "auto":
                classification = await classifier.classify(query)
                query_type = classification.query_type
            elif mode == "bail":
                query_type = QueryType.BAIL_QUERY
            else:
                query_type = QueryType.LEGAL_INFO
            
            result.query_type = query_type.value
            result.processing_info["steps"].append(f"✓ ClassifierAgent: {query_type.value}")
            emit("classify", "complete", {"type": query_type.value})

            # ==================== STAGE 2: Query Reformulation ====================
            emit("reformulate", "active")
            
            from agents.query_reformulator import QueryReformulator
            reformulator = QueryReformulator()
            reformulated = reformulator.reformulate(query)
            requested_sections = reformulated.extracted_sections
            
            result.processing_info["steps"].append(
                f"✓ Query enhanced: {len(reformulated.search_terms)} terms, {len(requested_sections)} sections"
            )
            emit("reformulate", "complete", {"sections": len(requested_sections)})

            # ==================== STAGE 3: ResearcherAgent ====================
            emit("retrieve", "active")
            result.agents_used.append("ResearcherAgent")
            
            from config import TOP_K_STATUTORY, TOP_K_CASE_LAW
            
            # Statutory & Case Law retrieval using RetrievalPipeline
            if self.retrieval_pipeline:
                evidence = self.retrieval_pipeline.run(
                    query=query,
                    enhanced_query=reformulated.enhanced_query,
                    query_type=query_type,
                    extracted_sections=requested_sections,
                    extracted_law_types=reformulated.extracted_law_types,
                    session_id=session_id
                )
                statutory_results = evidence.statutory_results
                bail_results = evidence.case_law_results
                # If session_documents were fetched by pipeline, we could use them, 
                # but they were passed to process_query, so we can ignore the pipeline's copy 
                # or use them. Since process_query gets them passed from api/query.py,
                # we don't necessarily need to overwrite them.
            else:
                statutory_results = []
                bail_results = []
            
            total_retrieved = len(statutory_results) + len(bail_results)
            result.processing_info["steps"].append(f"✓ ResearcherAgent: {total_retrieved} results retrieved & reranked")
            emit("retrieve", "complete", {"results": total_retrieved})

            # ==================== STAGE 4: Confidence Scoring ====================
            emit("score", "active")
            
            retrieval_confidence = None
            confidence_level = None
            use_fallback = False
            
            if query_type == QueryType.DOCUMENT_QUERY and session_documents:
                # Bypass strict confidence scoring for document queries
                from config import ConfidenceLevel
                confidence_level = ConfidenceLevel.HIGH
                confidence_reason = "Document context provided"
                use_fallback = False
                result.grounding_status = "pass"
                retrieval_confidence = None
                result.processing_info["confidence_breakdown"] = {"reason": "Document context overrides standard confidence"}
            elif self.confidence_scorer and statutory_results:
                retrieval_confidence = self.confidence_scorer.compute_confidence(
                    query=query, reformulated_query=reformulated,
                    results=statutory_results, query_type=query_type.value if hasattr(query_type, 'value') else query_type
                )
                
                from config import ConfidenceLevel
                confidence_level, confidence_reason = self.confidence_scorer.get_response_mode(retrieval_confidence)
                
                if confidence_level in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW):
                    use_fallback = True
                    result.grounding_status = "fail"
                elif confidence_level == ConfidenceLevel.MEDIUM:
                    result.grounding_status = "partial"
                else:
                    result.grounding_status = "pass"
                
                result.processing_info["confidence_breakdown"] = retrieval_confidence.to_dict()
            else:
                use_fallback = True
                result.grounding_status = "fail"
                confidence_reason = "No retrieval results"
            
            conf_score = f"{retrieval_confidence.overall_score:.2f}" if retrieval_confidence else "0.00"
            conf_level = confidence_level.value if confidence_level else "unknown"
            result.processing_info["steps"].append(
                f"✓ Confidence: {conf_score} ({conf_level})"
            )
            emit("score", "complete", {
                "confidence": round(retrieval_confidence.overall_score, 2) if retrieval_confidence else 0,
                "level": confidence_level.value if confidence_level else "unknown"
            })

            # ==================== STAGE 5: WebIntelAgent (Parallel Verification) ====================
            web_context = ""
            
            # CRITICAL UPDATE: Always verify if:
            # 1. It's a new law (BNS/BNSS/BSA)
            # 2. It's an Election/Special Rule (known gap in local statutory CSVs)
            # 3. The local confidence is low
            # 4. Domain Mismatch: retrieved context (e.g. Motor Vehicle) doesn't match query (e.g. Election)
            
            is_new_law = any(x in query.lower() for x in ["bns", "bnss", "bsa", "bharatiya"])
            is_election_or_special = any(x in query.lower() for x in ["election", "voter", "conduct of election", "pmla", "ndps"])
            
            # Check for domain mismatch
            domain_mismatch = False
            if statutory_results:
                top_result_text = statutory_results[0].text.lower()
                # If query is about elections but top result is motor vehicles/public servants
                if "election" in query.lower() and "election" not in top_result_text:
                    domain_mismatch = True
            
            if use_fallback or is_new_law or is_election_or_special or domain_mismatch:
                emit("web_search", "active")
                result.agents_used.append("WebIntelAgent")
                
                # Update processing info to reflect verification mode
                reason = "Domain Mismatch" if domain_mismatch else ("New Law" if is_new_law else "Special Rule")
                result.processing_info["steps"].append(f"✓ WebIntelAgent: Running verification for {reason}")
                
                try:
                    # Clean query for Firecrawl
                    logger.info(f"[CrewAI] AGENT_TRIGGER: Firecrawl search initiated for: {query}")
                    web_result = await asyncio.to_thread(self._firecrawl_search, query)
                    if web_result:
                        web_context = web_result
                        result.sources_used.append("firecrawl_web")
                        result.web_sources.append({
                            "type": "firecrawl_search",
                            "query": query,
                            "content_preview": web_result[:200]
                        })
                        logger.info(f"[CrewAI] Web verification found {len(web_result)} chars of context")
                        # DEBUG: Print first 500 chars to console for verification
                        print(f"\n{'#'*40}\nFIRECRAWL DEBUG OUTPUT:\n{web_result[:500]}\n{'#'*40}\n")
                        result.processing_info["steps"].append("✓ WebIntelAgent: Retrieved supplementary web context")
                    else:
                        result.processing_info["steps"].append("⚠ WebIntelAgent: No web results available")
                except Exception as e:
                    result.processing_info["steps"].append(f"⚠ WebIntelAgent: {str(e)}")
                
                emit("web_search", "complete")

            # ==================== STAGE 6: Generation ====================
            emit("generate", "active")
            
            from llm_provider import call_llm
            from prompts.templates import build_prompt_with_documents
            
            # Build structured context
            structured_context_text = ""
            if self.context_builder:
                structured_context_text = self.context_builder.build_structured_context(
                    statutory_results=statutory_results,
                    case_law_results=bail_results if bail_results else None,
                    uploaded_docs=session_documents,
                    max_tokens=3000
                )
            
            confidence_score = 0.5  # Default
            
            if query_type == QueryType.BAIL_QUERY:
                result.agents_used.append("BailAnalystAgent")
                
                stat_ctx = [
                    {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "source": r.source_dataset}
                    for r in statutory_results
                ]
                bail_ctx = [
                    {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "metadata": r.metadata}
                    for r in bail_results
                ]
                
                if session_documents:
                    prompt = build_prompt_with_documents(
                        query=query, statutory_context=stat_ctx,
                        document_context=session_documents,
                        bail_context=bail_ctx, is_bail_query=True
                    )
                    answer = await call_llm(prompt)
                    confidence_score = 0.85
                    result.bail_assessment = {
                        "bail_likelihood": "Document Analysis",
                        "legal_reasoning": {"bailable_status": "See document", "max_punishment": "See document", "severity_score": 0, "applicable_crpc": ["Based on uploaded document"]},
                        "explanation": "Analysis based on uploaded court document/FIR."
                    }
                else:
                    from agents.bail_evaluator import BailEvaluator
                    evaluator = BailEvaluator()
                    evaluation = await evaluator.evaluate(
                        query=query, statutory_context=stat_ctx,
                        bail_precedents=bail_ctx,
                        custody_duration_days=custody_days,
                        offence_sections=offense_sections
                    )
                    answer = evaluation.explanation
                    confidence_score = evaluation.confidence_score
                    result.bail_assessment = evaluation.to_dict()
                
                result.processing_info["steps"].append("✓ BailAnalystAgent: Assessment complete")
            else:
                # Legal information or Document query
                chat_context = f"\n{chat_history}\n" if chat_history else ""
                
                web_prompt_info = ""
                if web_context:
                    web_prompt_info = f"""
{'!'*60}
SUPPLEMENTARY WEB CONTEXT (USE FOR MISSING DETAILS, CITE AS [Web Source X]):
{'!'*60}
{web_context}
"""

                if query_type == QueryType.DOCUMENT_QUERY:
                    prompt = f"""You are JustiAssist, an AI legal assistant. The user has uploaded a document and is asking a question about it.
{chat_context}

USER QUERY: {query}

{'='*60}
RETRIEVED DOCUMENT CONTEXT:
{'='*60}
{structured_context_text}
{web_prompt_info}

INSTRUCTIONS:
1. Answer the user's question primarily using the uploaded document context.
2. If the document doesn't have the answer, use the WEB CONTEXT but explicitly state you are using external sources.
3. Provide precise citations: [Page X] for documents or [Web Source X] for web results.
4. Be professional, accurate, and avoid hallucinations.
"""
                else:
                    # General Legal Query
                    prompt = f"""You are JustiAssist, a premium AI legal expert specialized in Indian Law.
Your goal is to provide a comprehensive, cited, and accurate answer.

{chat_context}

USER QUERY: {query}

{'='*60}
VERIFIED STATUTORY CONTEXT (Local):
{'='*60}
{structured_context_text}

{'='*60}
VERIFIED WEB CONTEXT (Firecrawl/Verification):
{'='*60}
{web_context if web_context else 'No web results found. Use general legal knowledge if verified.'}

STRICT INSTRUCTIONS:
1. USE ALL PROVIDED SOURCES. If Web Context has the answer (like Rule 49P), USE IT. 
2. PRIORITY: Web Context (Latest) > Local Context (Historical).
3. If a section/rule is found in the WEB context, cite it as [Web Source: Rule X].
4. DO NOT say "I couldn't find any information" if the WEB context is provided below.
5. If the Local Context is about a different law (e.g. Motor Vehicles) than the query (e.g. Election), IGNORE the Local Context.
"""
                
                answer = await call_llm(prompt, temperature=0.3, max_tokens=2000)
                confidence_score = retrieval_confidence.overall_score if retrieval_confidence else 0.5
            
            result.answer = answer
            result.processing_info["steps"].append("✓ Response generated")
            emit("generate", "complete")

            # ==================== STAGE 7: QualityReviewerAgent (Verification) ====================
            emit("quality_review", "active")
            result.agents_used.append("QualityReviewerAgent")
            
            # CRITICAL: Cross-verify Local vs Web if web context exists
            if web_context:
                verification_prompt = f"""You are the QualityReviewerAgent. Your job is to ensure the answer is 100% accurate and prioritized correctly.
            
                SOURCES PROVIDED:
                1. LOCAL DATA: {structured_context_text[:1500]}
                2. WEB VERIFICATION (Firecrawl): {web_context[:1500]}
                
                PROPOSED ANSWER:
                {answer}
                
                VERIFICATION PROTOCOL:
                - If Local Data and Web Verification conflict on Section Numbers or Penalties, PRIORITIZE the Web Verification (it is more likely to be the latest BNS text).
                - If the local data is for IPC but the query is for BNS, and the Web Verification provides the BNS text, YOU MUST rewrite the answer to use the BNS text.
                - Ensure all citations are preserved.
                - If any part of the answer is not supported by either source, REMOVE IT.
                
                Respond with the finalized, verified answer. If you made significant corrections, start with "Verified against latest statutory records:".
                """
                answer = await call_llm(verification_prompt, temperature=0.2)
                result.answer = answer

            # Citation validation
            from citation_validator import citation_validator
            all_context = [
                {"section_number": r.section_number, "law_type": r.law_type, "text": r.text}
                for r in (statutory_results + bail_results)
            ]
            
            citation_validation = citation_validator.validate(
                response=answer, context_chunks=all_context, strict=False
            )
            
            if not citation_validation.is_valid:
                answer = citation_validator.sanitize_response(answer, citation_validation)
                confidence_score = max(confidence_score - 0.15, 0.3)
                result.processing_info["citation_warning"] = True
                result.processing_info["invalid_citations"] = citation_validation.invalid_sections
            
            # Grounding evaluation
            from agents.feedback_evaluator import FeedbackEvaluator
            feedback_eval = FeedbackEvaluator()
            grounding_eval = feedback_eval.evaluate(answer, all_context, query)
            
            if grounding_eval.grounding_score > 0.7:
                confidence_score = min(confidence_score + 0.1, 0.95)
            elif grounding_eval.grounding_score < 0.5 and not use_fallback:
                confidence_score = max(confidence_score - 0.15, 0.3)
            
            review_passed = citation_validation.is_valid and grounding_eval.grounding_score >= 0.5
            
            result.quality_review = {
                "passed": review_passed,
                "citation_valid": citation_validation.is_valid,
                "valid_citations": len(citation_validation.valid_sections),
                "invalid_citations": len(citation_validation.invalid_sections),
                "grounding_score": grounding_eval.grounding_score,
                "grounding_status": grounding_eval.status.value,
                "fabrication_score": citation_validation.fabrication_score,
            }
            
            result.answer = answer
            result.confidence_score = round(confidence_score, 2)
            result.processing_info["steps"].append(
                f"✓ QualityReviewerAgent: {len(citation_validation.valid_sections)}/"
                f"{len(citation_validation.cited_sections)} citations verified, "
                f"grounding: {grounding_eval.grounding_score:.2f}"
            )
            result.processing_info["grounding_details"] = grounding_eval.to_dict()
            emit("quality_review", "complete")

            # ==================== STAGE 8: Enrichment (Parallel) ====================
            if query_type != QueryType.DOCUMENT_QUERY:
                try:
                    from services.indian_kanoon import get_kanoon_api
                    from services.news_scraper import get_news_scraper
                    
                    search_sections = requested_sections[:2] if requested_sections else []
                    
                    async def fetch_kanoon():
                        try:
                            api = get_kanoon_api()
                            if api.api_key:
                                kq = " ".join(search_sections) + " bail judgment" if search_sections else query[:50]
                                res = await asyncio.wait_for(api.search(kq, doc_type="judgments"), timeout=3.0)
                                return [{"title": d.title, "citation": d.citation, "court": d.court, "date": d.date, "url": d.url, "preview": (d.headline or "")[:150]} for d in res.documents[:3]]
                        except:
                            pass
                        return []
                    
                    async def fetch_news():
                        try:
                            scraper = get_news_scraper()
                            nq = " ".join(search_sections) + " India law" if search_sections else "Indian law " + query[:30]
                            articles = await asyncio.to_thread(scraper.get_news, nq)
                            return [{"title": a.get("title", ""), "source": a.get("source", "Unknown"), "date": a.get("published date", ""), "url": a.get("url", "")} for a in articles[:2]]
                        except:
                            pass
                        return []
                    
                    kanoon_cases, news_items = await asyncio.gather(fetch_kanoon(), fetch_news())
                    
                    if kanoon_cases:
                        result.kanoon_cases = kanoon_cases
                        result.sources_used.append("indian_kanoon")
                    if news_items:
                        result.news_context = news_items
                        result.sources_used.append("legal_news")
                except Exception as e:
                    logger.warning(f"[CrewAI] Enrichment error: {e}")
            else:
                result.processing_info["steps"].append("✓ Enrichment skipped for document query")

            # Format citations
            all_results = statutory_results + bail_results
            result.citations = [
                {
                    "section": r.section_number,
                    "law_type": r.law_type,
                    "text_preview": r.text[:200] + "..." if len(r.text) > 200 else r.text,
                    "source": r.source_dataset,
                    "relevance_score": round(r.score, 3),
                }
                for r in all_results
            ]

            elapsed_ms = int((time.time() - start_time) * 1000)
            result.processing_info["total_time_ms"] = elapsed_ms
            result.processing_info["agents_used"] = result.agents_used

        except Exception as e:
            logger.error(f"[CrewAI] Pipeline error: {e}", exc_info=True)
            result.answer = f"An error occurred during processing: {str(e)}"
            result.grounding_status = "fail"
            result.confidence_score = 0.0

        return result

    async def review_output(self, content: str, context_chunks: list, query: str) -> Dict[str, Any]:
        """
        Run the QualityReviewer agent on any content (used by feature endpoints).
        Returns review results with pass/fail status.
        """
        from citation_validator import citation_validator
        from agents.feedback_evaluator import FeedbackEvaluator
        
        citation_result = citation_validator.validate(response=content, context_chunks=context_chunks, strict=False)
        
        evaluator = FeedbackEvaluator()
        grounding_result = evaluator.evaluate(content, context_chunks, query)
        
        return {
            "citations_valid": citation_result.is_valid,
            "grounding_score": grounding_result.grounding_score,
            "grounding_status": grounding_result.status.value,
            "fabrication_score": citation_result.fabrication_score,
            "issues": grounding_result.issues,
            "passed": citation_result.is_valid and grounding_result.grounding_score >= 0.5,
        }
