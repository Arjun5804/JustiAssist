from typing import List, Dict, Any, Optional
from retrieval.models import SearchResult, EvidenceSet, ValidatedEvidenceSet
from config import TOP_K_STATUTORY, TOP_K_CASE_LAW
from agents.query_classifier import QueryType
from document_session import session_manager

class RetrievalPipeline:
    def __init__(self, vector_store, reranker):
        self.vector_store = vector_store
        self.reranker = reranker

    def run(
        self,
        query: str,
        enhanced_query: str,
        query_type: str,
        extracted_sections: List[str],
        extracted_law_types: List[str],
        session_id: Optional[str] = None
    ) -> EvidenceSet:
        
        evidence = EvidenceSet()

        # 1. Session Documents (if available)
        if session_id:
            session = session_manager.get_session(session_id)
            if session and session.documents:
                doc_results = session.search(enhanced_query, top_k=5)
                evidence.session_documents = [
                    {"chunk_id": r.chunk_id, "filename": r.filename, "text": r.text, "document_type": r.document_type, "is_statutory": False, "score": r.score}
                    for r in doc_results
                ]

        # 2. Statutory Retrieval & Reranking
        if self.vector_store and self.vector_store.statutory_index is not None:
            initial_results = self.vector_store.hybrid_search_statutory(
                enhanced_query,
                top_k=TOP_K_STATUTORY * 3,
                semantic_weight=0.6,
                bm25_weight=0.4
            )
            
            if initial_results and self.reranker:
                rerank_mode = 'precision' if extracted_sections else 'balanced'
                evidence.statutory_results = self.reranker.rerank(
                    results=initial_results,
                    requested_sections=extracted_sections,
                    extracted_law_types=extracted_law_types,
                    top_k=TOP_K_STATUTORY,
                    mode=rerank_mode
                )
            else:
                evidence.statutory_results = initial_results or []
                
        # 3. Case Law Retrieval (if bail query)
        qtype_value = query_type.value if hasattr(query_type, 'value') else query_type
        if qtype_value == QueryType.BAIL_QUERY.value and self.vector_store:
            initial_case_law = self.vector_store.search_case_law(
                enhanced_query,
                top_k=TOP_K_CASE_LAW * 2
            )
            if initial_case_law and self.reranker:
                evidence.case_law_results = self.reranker.rerank(
                    results=initial_case_law, 
                    requested_sections=[],
                    top_k=TOP_K_CASE_LAW, 
                    mode='recall'
                )
            else:
                evidence.case_law_results = initial_case_law or []
                
        return evidence
