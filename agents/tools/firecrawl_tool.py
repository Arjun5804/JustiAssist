"""
JustiAssist — Firecrawl Tool for CrewAI
Web search and content extraction for queries not covered by local database.
"""

import os
from crewai.tools import BaseTool
from typing import Type, Optional
from pydantic import BaseModel, Field

from dotenv import load_dotenv
load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")


class FirecrawlSearchInput(BaseModel):
    """Input schema for FirecrawlSearchTool"""
    query: str = Field(..., description="Search query for finding legal information on the web")


class FirecrawlSearchTool(BaseTool):
    """Search the web for legal information not available in the local database."""
    
    name: str = "Web Legal Search"
    description: str = (
        "Search the internet for Indian legal information, recent amendments, latest judgments, "
        "or any legal topic not found in the local database. Returns web search results as clean text. "
        "Use this ONLY when the local Legal Database Search returns insufficient results."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchInput

    def _run(self, query: str) -> str:
        """Execute web search using Firecrawl"""
        if not FIRECRAWL_API_KEY or FIRECRAWL_API_KEY == "fc-your-api-key-here":
            return "Web search unavailable: Firecrawl API key not configured."
        
        try:
            from firecrawl import FirecrawlApp
            
            app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
            
            # Search with legal context
            search_query = f"India law legal {query}"
            results = app.search(query=search_query, limit=3)
            
            if not results or (hasattr(results, 'data') and not results.data):
                return f"No web results found for: '{query}'"
            
            # Format results
            formatted = []
            result_list = results.data if hasattr(results, 'data') else results
            
            for i, result in enumerate(result_list[:3], 1):
                if isinstance(result, dict):
                    title = result.get('title', 'Untitled')
                    url = result.get('url', '')
                    content = result.get('markdown', result.get('content', ''))[:800]
                else:
                    title = getattr(result, 'title', 'Untitled')
                    url = getattr(result, 'url', '')
                    content = getattr(result, 'markdown', getattr(result, 'content', ''))[:800]
                
                formatted.append(
                    f"[Web Source {i}] {title}\n"
                    f"URL: {url}\n"
                    f"Content: {content}\n"
                )
            
            header = f"Web Search Results for: '{query}'\n⚠️ These are web sources — verify before citing as authoritative.\n{'='*60}\n"
            return header + "\n---\n".join(formatted)
        
        except ImportError:
            return "Firecrawl SDK not installed. Run: pip install firecrawl-py"
        except Exception as e:
            return f"Web search error: {str(e)}"


class FirecrawlScrapeInput(BaseModel):
    """Input schema for FirecrawlScrapeTool"""
    url: str = Field(..., description="URL to extract content from")


class FirecrawlScrapeTool(BaseTool):
    """Extract and read content from a specific legal webpage URL."""
    
    name: str = "Web Page Reader"
    description: str = (
        "Extract and read the full content from a specific legal webpage URL. "
        "Use this to read judgment texts, gazette notifications, or legal articles. "
        "Returns the page content as clean markdown text."
    )
    args_schema: Type[BaseModel] = FirecrawlScrapeInput

    def _run(self, url: str) -> str:
        """Extract content from a URL using Firecrawl"""
        if not FIRECRAWL_API_KEY or FIRECRAWL_API_KEY == "fc-your-api-key-here":
            return "Web scraping unavailable: Firecrawl API key not configured."
            
        # Security: Domain Whitelist to prevent scraping abuse
        allowed_domains = [
            "indiankanoon.org", "livelaw.in", "barandbench.com", 
            "scobserver.in", "gov.in", "nic.in", "mha.gov.in", "sci.gov.in"
        ]
        
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname or ""
            
            is_allowed = any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)
            
            if not is_allowed:
                return f"Domain not authorized for scraping. Allowed domains: {', '.join(allowed_domains[:3])} and other Indian legal/government sites."
                
            from firecrawl import FirecrawlApp
            
            app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
            result = app.scrape_url(url)
            
            if not result:
                return f"Could not extract content from: {url}"
            
            if isinstance(result, dict):
                content = result.get('markdown', result.get('content', ''))
            else:
                content = getattr(result, 'markdown', getattr(result, 'content', ''))
            
            # Truncate to reasonable size for LLM context
            if len(content) > 4000:
                content = content[:4000] + "\n\n... [Content truncated for brevity]"
            
            return f"Content from: {url}\n{'='*60}\n{content}"
        
        except ImportError:
            return "Firecrawl SDK not installed. Run: pip install firecrawl-py"
        except Exception as e:
            return f"Web scraping error for {url}: {str(e)}"
