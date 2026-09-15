import os
import logging
import asyncio
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class FirecrawlService:
    def __init__(self):
        self._firecrawl_available = False
        self._init_firecrawl()

    def _init_firecrawl(self):
        """Check if Firecrawl is available"""
        api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if api_key and api_key != "fc-your-api-key-here":
            self._firecrawl_available = True
            logger.info("[FirecrawlService] Firecrawl tool available")
        else:
            logger.info("[FirecrawlService] Firecrawl not configured (optional)")

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the web using Firecrawl and return structured results."""
        if not self._firecrawl_available:
            return []
            
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
            
            # Use same multi-stage search strategy logic from previous orchestrator
            primary_query = f"India {query} full text definition penalty"
            secondary_query = f"India legal rule section {query} manual"
            
            final_query = primary_query
            if any(x in query.lower() for x in ["rule", "election", "p", "conduct"]):
                final_query = f"Rule {query} Conduct of Elections Rules India"
                
            logger.info(f"[FirecrawlService] Searching for: {final_query}")
            results = app.search(query=final_query, limit=8)
            
            if not results:
                return []
                
            result_list = []
            if isinstance(results, dict):
                result_list = results.get('data', [])
            elif hasattr(results, 'data'):
                result_list = results.data
            elif isinstance(results, list):
                result_list = results
            else:
                try:
                    result_list = list(results)
                except:
                    result_list = []
                    
            formatted_results = []
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
                        formatted_results.append({
                            "title": title,
                            "url": url,
                            "content": content
                        })
                except Exception as inner_e:
                    logger.warning(f"[FirecrawlService] Error processing result {i}: {inner_e}")
                    continue
                    
            return formatted_results
        except Exception as e:
            logger.warning(f"[FirecrawlService] Search error: {e}")
            return []

# Singleton instance
_firecrawl_instance = None

def get_firecrawl_service() -> FirecrawlService:
    global _firecrawl_instance
    if _firecrawl_instance is None:
        _firecrawl_instance = FirecrawlService()
    return _firecrawl_instance
