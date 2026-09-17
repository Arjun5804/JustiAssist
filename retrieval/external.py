import asyncio
import hashlib
import logging
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Dict, Any

from retrieval.models import SearchResult, Provenance, AuthorityLevel
from services.firecrawl import get_firecrawl_service
from services.indian_kanoon import get_kanoon_api
from services.news_scraper import get_news_scraper

logger = logging.getLogger(__name__)

class AuthorityClassifier:
    """Deterministically classifies source authority based on domain."""
    
    PRIMARY_DOMAINS = ["india.gov.in", "supreme.court.gov.in", "highcourts.gov.in", "egazette.nic.in"]
    TRUSTED_DOMAINS = ["indiankanoon.org", "livelaw.in", "barandbench.com", "scconline.com"]
    NEWS_DOMAINS = ["thehindu.com", "timesofindia.indiatimes.com", "ndtv.com"]
    
    @classmethod
    def classify(cls, url: str, source_type: str) -> AuthorityLevel:
        if source_type == "indian_kanoon":
            return AuthorityLevel.TRUSTED_LEGAL
        if source_type == "legal_news":
            return AuthorityLevel.NEWS
            
        try:
            domain = urlparse(url).netloc.lower()
            if not domain:
                return AuthorityLevel.UNKNOWN
                
            for d in cls.PRIMARY_DOMAINS:
                if domain == d or domain.endswith(f".{d}"):
                    return AuthorityLevel.PRIMARY_OFFICIAL
                    
            for d in cls.TRUSTED_DOMAINS:
                if domain == d or domain.endswith(f".{d}"):
                    return AuthorityLevel.TRUSTED_LEGAL
                    
            for d in cls.NEWS_DOMAINS:
                if domain == d or domain.endswith(f".{d}"):
                    return AuthorityLevel.NEWS
                    
        except Exception:
            pass
            
        return AuthorityLevel.UNKNOWN

class ExternalEvidenceNormalizer:
    """Normalizes raw external results into structured SearchResults."""
    
    @staticmethod
    def _generate_chunk_id(source_type: str, url: str, text: str) -> str:
        content = f"{url}:{text}"
        hash_val = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"ext_{source_type}_{hash_val}"

    @classmethod
    def normalize_firecrawl(cls, result: dict) -> SearchResult:
        url = result.get("url", "")
        text = result.get("content", "")
        title = result.get("title", "")
        
        authority = AuthorityClassifier.classify(url, "firecrawl")
        chunk_id = cls._generate_chunk_id("web", url, text)
        
        return SearchResult(
            chunk_id=chunk_id,
            text=text,
            score=0.0,
            law_type="Web Context",
            section_number="N/A",
            source_dataset="Firecrawl",
            dataset_type="external_web",
            metadata={"url": url, "title": title, "source_type": "firecrawl"},
            provenance=Provenance(
                source_authority=authority,
                retrieved_at=datetime.utcnow().isoformat()
            )
        )
        
    @classmethod
    def normalize_kanoon(cls, result: dict) -> SearchResult:
        url = result.get("url", "")
        text = result.get("preview", "") # We use preview or fetch full text
        title = result.get("title", "")
        date = result.get("date")
        
        authority = AuthorityClassifier.classify(url, "indian_kanoon")
        chunk_id = cls._generate_chunk_id("kanoon", url, text)
        
        return SearchResult(
            chunk_id=chunk_id,
            text=text,
            score=0.0,
            law_type="Case Law",
            section_number="N/A",
            source_dataset="Indian Kanoon",
            dataset_type="indian_kanoon",
            metadata={"url": url, "title": title, "court": result.get("court"), "citation": result.get("citation"), "source_type": "indian_kanoon"},
            provenance=Provenance(
                source_authority=authority,
                source_date=date,
                retrieved_at=datetime.utcnow().isoformat()
            )
        )
        
    @classmethod
    def normalize_news(cls, result: dict) -> SearchResult:
        url = result.get("url", "")
        text = f"{result.get('title', '')} - {result.get('summary', '')}"
        title = result.get("title", "")
        date = result.get("date", result.get("published_date"))
        
        authority = AuthorityClassifier.classify(url, "legal_news")
        chunk_id = cls._generate_chunk_id("news", url, text)
        
        return SearchResult(
            chunk_id=chunk_id,
            text=text,
            score=0.0,
            law_type="News",
            section_number="N/A",
            source_dataset="Google News",
            dataset_type="legal_news",
            metadata={"url": url, "title": title, "source": result.get("source"), "source_type": "legal_news"},
            provenance=Provenance(
                source_authority=authority,
                source_date=date,
                retrieved_at=datetime.utcnow().isoformat()
            )
        )


class ExternalRetriever:
    """Orchestrates fetching from external providers."""
    
    @staticmethod
    async def retrieve(
        query: str,
        requested_sections: List[str] = None,
        trigger_web_search: bool = False,
        fetch_kanoon: bool = True,
        fetch_news: bool = True
    ) -> List[SearchResult]:
        
        results: List[SearchResult] = []
        tasks = []
        
        # Firecrawl
        if trigger_web_search:
            tasks.append(ExternalRetriever._fetch_firecrawl(query))
        else:
            tasks.append(asyncio.sleep(0, result=[]))
            
        # Kanoon
        if fetch_kanoon:
            tasks.append(ExternalRetriever._fetch_kanoon(query, requested_sections))
        else:
            tasks.append(asyncio.sleep(0, result=[]))
            
        # News
        if fetch_news:
            tasks.append(ExternalRetriever._fetch_news(query, requested_sections))
        else:
            tasks.append(asyncio.sleep(0, result=[]))
            
        firecrawl_res, kanoon_res, news_res = await asyncio.gather(*tasks)
        
        for r in firecrawl_res:
            results.append(ExternalEvidenceNormalizer.normalize_firecrawl(r))
            
        for r in kanoon_res:
            results.append(ExternalEvidenceNormalizer.normalize_kanoon(r))
            
        for r in news_res:
            results.append(ExternalEvidenceNormalizer.normalize_news(r))
            
        return results

    @staticmethod
    async def _fetch_firecrawl(query: str) -> List[Dict[str, Any]]:
        try:
            service = get_firecrawl_service()
            return await asyncio.wait_for(asyncio.to_thread(service.search, query), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("[ExternalRetriever] Firecrawl search timed out")
            return []
        except Exception as e:
            logger.warning(f"[ExternalRetriever] Firecrawl error: {e}")
            return []
            
    @staticmethod
    async def _fetch_kanoon(query: str, requested_sections: List[str]) -> List[Dict[str, Any]]:
        try:
            api = get_kanoon_api()
            if not api.api_key:
                return []
            
            kanoon_query = " ".join(requested_sections[:2]) + " bail judgment" if requested_sections else query[:50]
            res = await asyncio.wait_for(api.search(kanoon_query, doc_type="judgments"), timeout=3.0)
            return [{
                "title": d.title,
                "citation": d.citation,
                "court": d.court,
                "date": d.date,
                "url": d.url,
                "preview": (d.headline or "")[:300]
            } for d in res.documents[:3]]
        except Exception as e:
            logger.warning(f"[ExternalRetriever] Kanoon error: {e}")
            return []

    @staticmethod
    async def _fetch_news(query: str, requested_sections: List[str]) -> List[Dict[str, Any]]:
        try:
            scraper = get_news_scraper()
            news_query = " ".join(requested_sections[:2]) + " India law" if requested_sections else "Indian law " + query[:30]
            articles = await asyncio.wait_for(asyncio.to_thread(scraper.fetch_news, news_query), timeout=10.0)
            
            # Check if these are fallback articles
            # Fallback articles are identified if no query was sent, but we sent a query.
            # If the scraper failed and returned fallback, we shouldn't use them as evidence.
            # We can check by url or just rely on the scraper logic.
            # The scraper uses fallback when gnews fails.
            
            valid_articles = []
            for a in articles[:2]:
                # Exclude fallback news completely
                if getattr(a, 'is_fallback', False):
                    continue
                valid_articles.append({
                    "title": a.title,
                    "summary": a.summary,
                    "source": a.source,
                    "date": a.published_date,
                    "url": a.url
                })
            return valid_articles
        except asyncio.TimeoutError:
            logger.warning("[ExternalRetriever] News search timed out")
            return []
        except Exception as e:
            logger.warning(f"[ExternalRetriever] News error: {e}")
            return []
