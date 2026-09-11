"""
JustiAssist — Vector Search Tool for CrewAI
Wraps the existing VectorStore to be used by CrewAI agents.
"""

from crewai.tools import BaseTool
from typing import Type, Optional
from pydantic import BaseModel, Field


class VectorSearchInput(BaseModel):
    """Input schema for VectorSearchTool"""
    query: str = Field(..., description="Legal search query (e.g. 'Section 302 IPC murder punishment')")
    search_type: str = Field(default="statutory", description="Type of search: 'statutory' or 'case_law'")
    top_k: int = Field(default=10, description="Number of results to retrieve")


class VectorSearchTool(BaseTool):
    """Search the local Indian law vector database for statutory provisions and case law."""
    
    name: str = "Legal Database Search"
    description: str = (
        "Search the local Indian law database for statutory provisions (IPC, CrPC, BNS, BNSS, Constitution) "
        "and case law precedents. Use this tool FIRST before any web search. "
        "Returns relevant legal text with section numbers and law types."
    )
    args_schema: Type[BaseModel] = VectorSearchInput

    # Injected at runtime by the orchestrator
    vector_store: Optional[object] = None
    reranker: Optional[object] = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str, search_type: str = "statutory", top_k: int = 10) -> str:
        """Execute the vector search"""
        if not self.vector_store:
            return "ERROR: Vector store not initialized. Cannot search local database."
        
        try:
            if search_type == "case_law":
                results = self.vector_store.search_case_law(query, top_k=top_k)
            else:
                results = self.vector_store.hybrid_search_statutory(
                    query, top_k=top_k * 2,
                    semantic_weight=0.6, bm25_weight=0.4
                )
                
                # Apply reranking if available
                if self.reranker and results:
                    from reranker import SearchResult as RerankSearchResult
                    rerank_inputs = [
                        RerankSearchResult(
                            chunk_id=r.chunk_id, text=r.text, score=r.score,
                            law_type=r.law_type, section_number=r.section_number,
                            source_dataset=r.source_dataset, dataset_type=r.dataset_type,
                            metadata=r.metadata
                        ) for r in results
                    ]
                    results = self.reranker.rerank(
                        results=rerank_inputs,
                        requested_sections=[],
                        top_k=top_k,
                        mode='balanced'
                    )
            
            if not results:
                return f"No results found for query: '{query}'. The local database may not have relevant provisions."
            
            # Format results
            formatted = []
            for i, r in enumerate(results[:top_k], 1):
                formatted.append(
                    f"[{i}] {r.law_type} — {r.section_number}\n"
                    f"Source: {r.source_dataset}\n"
                    f"Text: {r.text[:600]}\n"
                    f"Relevance Score: {r.score:.3f}\n"
                )
            
            header = f"Found {len(results)} results for: '{query}'\n{'='*60}\n"
            return header + "\n---\n".join(formatted)
        
        except Exception as e:
            return f"ERROR searching vector database: {str(e)}"
