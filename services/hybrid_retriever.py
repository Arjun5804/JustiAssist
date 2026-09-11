"""
Hybrid Retriever Service

Orchestrates multi-source retrieval:
1. Local vector store (statutory + case law)
2. Indian Kanoon API (live case citations)
3. Legal news (current developments)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class KanoonCase:
    """A case from Indian Kanoon"""
    title: str
    citation: Optional[str]
    court: Optional[str]
    date: Optional[str]
    url: str
    headline: str
    relevance_note: str = ""


@dataclass
class NewsItem:
    """A legal news item"""
    title: str
    source: str
    date: str
    url: str
    relevance_note: str = ""


@dataclass
class HybridContext:
    """Combined context from all sources"""
    local_results: List[Any] = field(default_factory=list)
    kanoon_cases: List[KanoonCase] = field(default_factory=list)
    news_items: List[NewsItem] = field(default_factory=list)
    sources_used: List[str] = field(default_factory=list)
    fetch_times: Dict[str, float] = field(default_factory=dict)
    
    def to_prompt_context(self) -> str:
        """Format as context for LLM prompt"""
        sections = []
        
        # Local statutory context
        if self.local_results:
            sections.append("## Retrieved Legal Provisions\n")
            for i, result in enumerate(self.local_results[:5], 1):
                text = result.text if hasattr(result, 'text') else str(result)
                sections.append(f"{i}. {text[:500]}...\n")
        
        # Kanoon cases
        if self.kanoon_cases:
            sections.append("\n## Recent Case Law (Indian Kanoon)\n")
            for case in self.kanoon_cases[:3]:
                sections.append(f"- **{case.title}**")
                if case.citation:
                    sections.append(f"  Citation: {case.citation}")
                if case.court:
                    sections.append(f"  Court: {case.court}")
                sections.append(f"  {case.headline[:200]}...\n")
        
        # News context
        if self.news_items:
            sections.append("\n## Current Legal Developments\n")
            for news in self.news_items[:2]:
                sections.append(f"- {news.title} ({news.source}, {news.date})\n")
        
        return "\n".join(sections)
    
    def to_response_dict(self) -> Dict:
        """Format for API response"""
        return {
            "kanoon_cases": [
                {
                    "title": c.title,
                    "citation": c.citation,
                    "court": c.court,
                    "date": c.date,
                    "url": c.url,
                    "preview": c.headline[:150] if c.headline else "",
                }
                for c in self.kanoon_cases
            ],
            "news_context": [
                {
                    "title": n.title,
                    "source": n.source,
                    "date": n.date,
                    "url": n.url,
                }
                for n in self.news_items
            ],
            "sources_used": self.sources_used,
            "fetch_times_ms": {k: int(v * 1000) for k, v in self.fetch_times.items()},
        }


class HybridRetriever:
    """
    Orchestrates retrieval from multiple sources.
    
    Usage:
        retriever = HybridRetriever(vector_store, kanoon_api, news_scraper)
        context = await retriever.retrieve(query, sections=["IPC 302"])
    """
    
    def __init__(
        self,
        vector_store=None,
        kanoon_api=None,
        news_scraper=None,
        kanoon_timeout: float = 3.0,
        news_timeout: float = 2.0,
    ):
        self.vector_store = vector_store
        self.kanoon_api = kanoon_api
        self.news_scraper = news_scraper
        self.kanoon_timeout = kanoon_timeout
        self.news_timeout = news_timeout
    
    async def retrieve(
        self,
        query: str,
        sections: List[str] = None,
        query_type: str = "general",
        include_kanoon: bool = True,
        include_news: bool = True,
        k: int = 10,
    ) -> HybridContext:
        """
        Retrieve from all sources in parallel.
        
        Args:
            query: User's legal query
            sections: Extracted section numbers (e.g., ["IPC 302", "CrPC 437"])
            query_type: Type of query for relevance filtering
            include_kanoon: Whether to fetch from Indian Kanoon
            include_news: Whether to fetch legal news
            k: Number of local results to retrieve
        """
        context = HybridContext()
        tasks = []
        
        # Local vector search (always)
        if self.vector_store:
            tasks.append(self._fetch_local(query, query_type, k))
            context.sources_used.append("local_vectors")
        
        # Indian Kanoon (parallel)
        if include_kanoon and self.kanoon_api:
            kanoon_query = self._build_kanoon_query(query, sections)
            tasks.append(self._fetch_kanoon(kanoon_query))
            context.sources_used.append("indian_kanoon")
        
        # Legal news (parallel)
        if include_news and self.news_scraper:
            tasks.append(self._fetch_news(query, sections))
            context.sources_used.append("legal_news")
        
        # Run all in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Fetch error: {result}")
                    continue
                
                if isinstance(result, tuple):
                    result_type, data, elapsed = result
                    context.fetch_times[result_type] = elapsed
                    
                    if result_type == "local":
                        context.local_results = data
                    elif result_type == "kanoon":
                        context.kanoon_cases = data
                    elif result_type == "news":
                        context.news_items = data
        
        return context
    
    async def _fetch_local(self, query: str, query_type: str, k: int):
        """Fetch from local vector store"""
        import time
        start = time.time()
        
        results = []
        if self.vector_store:
            # Use appropriate search method based on query type
            if query_type in ["bail_related", "bail_eligibility"]:
                results = self.vector_store.search_bail(query, k=k)
            else:
                results = self.vector_store.search_statutory(query, k=k)
        
        return ("local", results, time.time() - start)
    
    async def _fetch_kanoon(self, query: str):
        """Fetch from Indian Kanoon API with timeout"""
        import time
        start = time.time()
        cases = []
        
        try:
            result = await asyncio.wait_for(
                self.kanoon_api.search(query, doc_type="judgments"),
                timeout=self.kanoon_timeout
            )
            
            for doc in result.documents[:5]:
                cases.append(KanoonCase(
                    title=doc.title,
                    citation=doc.citation,
                    court=doc.court,
                    date=doc.date,
                    url=doc.url,
                    headline=doc.headline or "",
                ))
        except asyncio.TimeoutError:
            logger.warning("Indian Kanoon fetch timed out")
        except Exception as e:
            logger.warning(f"Indian Kanoon fetch failed: {e}")
        
        return ("kanoon", cases, time.time() - start)
    
    async def _fetch_news(self, query: str, sections: List[str] = None):
        """Fetch relevant legal news"""
        import time
        start = time.time()
        items = []
        
        try:
            # Build news search query
            if sections:
                news_query = " ".join(sections[:2]) + " India law"
            else:
                news_query = query[:50] + " India legal"
            
            news_articles = await asyncio.wait_for(
                asyncio.to_thread(self.news_scraper.fetch_news),
                timeout=self.news_timeout
            )
            
            for article in news_articles[:3]:
                items.append(NewsItem(
                    title=article.title,
                    source=article.source,
                    date=article.published_date,
                    url=article.url,
                ))
        except asyncio.TimeoutError:
            logger.warning("News fetch timed out")
        except Exception as e:
            logger.warning(f"News fetch failed: {e}")
        
        return ("news", items, time.time() - start)
    
    def _build_kanoon_query(self, query: str, sections: List[str] = None) -> str:
        """Build optimized query for Indian Kanoon"""
        if sections:
            # Search for specific sections + bail/judgment context
            section_terms = " OR ".join(sections[:3])
            return f"({section_terms}) AND (bail OR judgment)"
        else:
            # Use first 50 chars of query
            return query[:50]


# Factory function
def create_hybrid_retriever(vector_store=None) -> HybridRetriever:
    """Create a HybridRetriever with available services"""
    kanoon_api = None
    news_scraper = None
    
    try:
        from services.indian_kanoon import get_kanoon_api
        api = get_kanoon_api()
        if api.api_key:
            kanoon_api = api
    except Exception as e:
        logger.info(f"Indian Kanoon not available: {e}")
    
    try:
        from services.news_scraper import get_news_scraper
        news_scraper = get_news_scraper()
    except Exception as e:
        logger.info(f"News scraper not available: {e}")
    
    return HybridRetriever(
        vector_store=vector_store,
        kanoon_api=kanoon_api,
        news_scraper=news_scraper,
    )
