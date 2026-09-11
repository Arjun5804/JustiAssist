"""
Indian Kanoon API Service

Provides methods to search and retrieve legal documents from indiankanoon.org.
API Documentation: https://api.indiankanoon.org/doc/
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import httpx

logger = logging.getLogger(__name__)

@dataclass
class KanoonDocument:
    """Represents a document from Indian Kanoon"""
    doc_id: str
    title: str
    doc_type: str  # 'judgments', 'acts', etc.
    headline: str
    text: Optional[str] = None
    citation: Optional[str] = None
    court: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SearchResult:
    """Indian Kanoon search result"""
    query: str
    total_results: int
    page: int
    documents: List[KanoonDocument]
    search_time_ms: int


class IndianKanoonAPI:
    """
    Client for Indian Kanoon API.
    
    Usage:
        api = IndianKanoonAPI(api_key="your_key")
        results = await api.search("bail Section 437 CrPC")
        doc = await api.get_document("12345")
    """
    
    BASE_URL = "https://api.indiankanoon.org"
    
    # Document types
    DOC_TYPES = {
        'all': '',
        'judgments': 'judgments',
        'acts': 'acts',
        'central': 'central',
        'sc': 'supremecourt',
        'hc': 'highcourt',
    }
    
    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None):
        """
        Initialize Indian Kanoon API client.
        
        Args:
            api_key: API key from indiankanoon.org (or set INDIAN_KANOON_API_KEY env var)
            cache_dir: Directory for caching responses (default: data/kanoon_cache)
        """
        self.api_key = api_key or os.getenv('INDIAN_KANOON_API_KEY')
        
        if not self.api_key:
            logger.warning("Indian Kanoon API key not set. API calls will fail.")
        
        # Setup cache
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent / "data" / "kanoon_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Rate limiting: max 60 requests per minute
        self._request_count = 0
        self._request_window_start = datetime.now()
    
    async def search(
        self,
        query: str,
        page: int = 0,
        doc_type: str = 'all',
        court: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> SearchResult:
        """
        Search Indian Kanoon for legal documents.
        
        Args:
            query: Search query (supports section numbers, case names, etc.)
            page: Page number (0-indexed)
            doc_type: Filter by type ('all', 'judgments', 'acts', 'sc', 'hc')
            court: Filter by specific court
            from_date: Filter from date (YYYY-MM-DD)
            to_date: Filter to date (YYYY-MM-DD)
            
        Returns:
            SearchResult with matching documents
        """
        import time
        start_time = time.time()
        
        # Build search params
        params = {
            'formInput': query,
            'pagenum': page,
        }
        
        if doc_type and doc_type != 'all':
            params['doctype'] = self.DOC_TYPES.get(doc_type, doc_type)
        
        if court:
            params['court'] = court
        
        if from_date:
            params['fromdate'] = from_date
        
        if to_date:
            params['todate'] = to_date
        
        # Check cache
        cache_key = self._get_cache_key('search', params)
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for search: {query[:30]}...")
            return self._parse_search_result(query, cached, int((time.time() - start_time) * 1000))
        
        # Make API request
        try:
            await self._check_rate_limit()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/search/",
                    data=params,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
            
            # Cache the response
            self._save_to_cache(cache_key, data)
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            return self._parse_search_result(query, data, elapsed_ms)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Indian Kanoon API error: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Indian Kanoon search failed: {e}")
            raise
    
    async def get_document(self, doc_id: str, include_text: bool = True) -> Optional[KanoonDocument]:
        """
        Get a specific document by ID.
        
        Args:
            doc_id: Document ID from Indian Kanoon
            include_text: Whether to include full text (larger response)
            
        Returns:
            KanoonDocument or None if not found
        """
        cache_key = self._get_cache_key('doc', {'id': doc_id, 'text': include_text})
        cached = self._get_from_cache(cache_key)
        
        if cached:
            return self._parse_document(cached)
        
        try:
            await self._check_rate_limit()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/doc/{doc_id}/",
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
            
            self._save_to_cache(cache_key, data)
            return self._parse_document(data)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            raise
    
    async def search_by_citation(self, citation: str) -> Optional[KanoonDocument]:
        """
        Search for a document by its legal citation.
        
        Args:
            citation: Legal citation (e.g., "AIR 2017 SC 4161", "2019 SCC 123")
            
        Returns:
            Matching document or None
        """
        # Search with citation as query
        results = await self.search(f'"{citation}"', doc_type='judgments')
        
        if results.documents:
            # Get full document for best match
            return await self.get_document(results.documents[0].doc_id)
        
        return None
    
    async def get_section_law(self, section: str, law: str = 'IPC') -> List[KanoonDocument]:
        """
        Get documents related to a specific section of a law.
        
        Args:
            section: Section number (e.g., "302", "420")
            law: Law name (e.g., "IPC", "CrPC", "BNS")
            
        Returns:
            List of relevant documents
        """
        query = f'Section {section} {law}'
        results = await self.search(query, doc_type='all')
        return results.documents
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        if self.api_key:
            headers['Authorization'] = f'Token {self.api_key}'
        return headers
    
    async def _check_rate_limit(self):
        """Simple rate limiting - 60 requests per minute"""
        import asyncio
        
        now = datetime.now()
        if (now - self._request_window_start).seconds >= 60:
            self._request_count = 0
            self._request_window_start = now
        
        if self._request_count >= 60:
            wait_time = 60 - (now - self._request_window_start).seconds
            logger.info(f"Rate limit reached, waiting {wait_time}s")
            await asyncio.sleep(wait_time)
            self._request_count = 0
            self._request_window_start = datetime.now()
        
        self._request_count += 1
    
    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        """Generate cache key from endpoint and params"""
        content = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_from_cache(self, key: str, max_age_hours: int = 24) -> Optional[Dict]:
        """Get cached response if valid"""
        cache_file = self.cache_dir / f"{key}.json"
        
        if cache_file.exists():
            age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if age < timedelta(hours=max_age_hours):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    
    def _save_to_cache(self, key: str, data: Dict):
        """Save response to cache"""
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")
    
    def _parse_search_result(self, query: str, data: Dict, elapsed_ms: int) -> SearchResult:
        """Parse API search response"""
        documents = []
        
        for doc in data.get('docs', []):
            documents.append(KanoonDocument(
                doc_id=str(doc.get('tid', '')),
                title=doc.get('title', ''),
                doc_type=doc.get('doctype', 'unknown'),
                headline=doc.get('headline', ''),
                citation=doc.get('citation'),
                court=doc.get('authority'),
                date=doc.get('date'),
                url=f"https://indiankanoon.org/doc/{doc.get('tid', '')}/",
            ))
        
        return SearchResult(
            query=query,
            total_results=data.get('found', 0),
            page=data.get('pagenum', 0),
            documents=documents,
            search_time_ms=elapsed_ms,
        )
    
    def _parse_document(self, data: Dict) -> KanoonDocument:
        """Parse API document response"""
        return KanoonDocument(
            doc_id=str(data.get('tid', '')),
            title=data.get('title', ''),
            doc_type=data.get('doctype', 'unknown'),
            headline=data.get('headline', ''),
            text=data.get('doc', ''),
            citation=data.get('citation'),
            court=data.get('authority'),
            date=data.get('date'),
            url=f"https://indiankanoon.org/doc/{data.get('tid', '')}/",
        )


# Singleton instance
_api_instance: Optional[IndianKanoonAPI] = None

def get_kanoon_api() -> IndianKanoonAPI:
    """Get or create the Indian Kanoon API singleton"""
    global _api_instance
    if _api_instance is None:
        _api_instance = IndianKanoonAPI()
    return _api_instance
