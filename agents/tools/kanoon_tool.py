"""
JustiAssist — Indian Kanoon Tool for CrewAI
Wraps the existing Indian Kanoon API for agent use.
"""

import asyncio
from crewai.tools import BaseTool
from typing import Type, Optional
from pydantic import BaseModel, Field


class KanoonSearchInput(BaseModel):
    """Input schema for KanoonSearchTool"""
    query: str = Field(..., description="Search query for Indian Kanoon (e.g. 'Section 302 IPC bail judgment')")
    doc_type: str = Field(default="judgments", description="Type: 'judgments', 'acts', 'all'")


class KanoonSearchTool(BaseTool):
    """Search Indian Kanoon for real court judgments and legal documents."""
    
    name: str = "Indian Kanoon Case Search"
    description: str = (
        "Search the Indian Kanoon database for real court judgments, case law, and legal documents. "
        "Returns actual case citations with court name, date, and preview. "
        "Use this to find precedent cases and real judgments."
    )
    args_schema: Type[BaseModel] = KanoonSearchInput

    def _run(self, query: str, doc_type: str = "judgments") -> str:
        """Execute Indian Kanoon search"""
        try:
            from services.indian_kanoon import get_kanoon_api
            api = get_kanoon_api()
            
            if not api.api_key:
                return "Indian Kanoon API key not configured. Cannot search case law."
            
            # Run async search in sync context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an async context, use a thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(
                            lambda: asyncio.run(api.search(query, doc_type=doc_type))
                        ).result(timeout=10)
                else:
                    result = asyncio.run(api.search(query, doc_type=doc_type))
            except RuntimeError:
                result = asyncio.run(api.search(query, doc_type=doc_type))
            
            if not result or not result.documents:
                return f"No cases found on Indian Kanoon for: '{query}'"
            
            formatted = []
            for i, doc in enumerate(result.documents[:5], 1):
                formatted.append(
                    f"[Case {i}] {doc.title}\n"
                    f"Citation: {doc.citation or 'N/A'}\n"
                    f"Court: {doc.court or 'N/A'}\n"
                    f"Date: {doc.date or 'N/A'}\n"
                    f"URL: {doc.url}\n"
                    f"Preview: {(doc.headline or '')[:300]}\n"
                )
            
            header = f"Indian Kanoon Results for: '{query}' ({result.total_results} total)\n{'='*60}\n"
            return header + "\n---\n".join(formatted)
        
        except Exception as e:
            return f"Indian Kanoon search error: {str(e)}"
