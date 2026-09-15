"""
Legal News Scraper Service

Fetches legal news from Google News using the gnews library,
with optional BeautifulSoup article extraction.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class NewsArticle:
    """Represents a legal news article"""
    title: str
    summary: str
    url: str
    source: str
    published_date: str
    category: str = "legal"
    vector_id: Optional[str] = None
    is_fallback: bool = False

class LegalNewsScraper:
    """
    Fetches and caches legal news from Google News.
    Uses gnews library for initial fetch.
    """
    
    LEGAL_KEYWORDS = [
        "Supreme Court India",
        "High Court judgment", 
        "bail granted",
        "IPC section",
        "BNS criminal",
        "legal verdict",
        "court ruling India",
        "anticipatory bail",
        "habeas corpus",
        "Indian judiciary",
    ]
    
    def __init__(self, cache_path: str = None):
        """
        Initialize the news scraper.
        
        Args:
            cache_path: Path to cache JSON file. Defaults to data/legal_news.json
        """
        if cache_path is None:
            base_dir = Path(__file__).parent.parent
            cache_path = base_dir / "data" / "legal_news.json"
        
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Try to import gnews
        self._gnews = None
        try:
            from gnews import GNews
            self._gnews = GNews(language='en', country='IN', max_results=20)
            logger.info("GNews library initialized successfully")
        except ImportError:
            logger.warning("gnews not installed. Using fallback news sources.")
    
    def fetch_news(self, query: str = None, force_refresh: bool = False) -> List[NewsArticle]:
        """
        Fetch legal news articles, optionally filtered by query.
        
        Args:
            query: Specific search query (e.g. "bail section 437")
            force_refresh: If True, bypass cache and fetch fresh news
            
        Returns:
            List of NewsArticle objects
        """
        # Check cache first ONLY if no specific query (we don't cache search queries yet)
        if not force_refresh and not query:
            cached = self._load_cache()
            if cached:
                logger.info(f"Loaded {len(cached)} articles from cache")
                return cached
        
        articles = []
        
        if self._gnews:
            if query:
                try:
                    # Specific query search
                    logger.info(f"Fetching news for query: {query}")
                    items = self._gnews.get_news(query)
                    for item in items[:5]:
                        article = NewsArticle(
                            title=item.get('title', ''),
                            summary=item.get('description', '')[:200] if item.get('description') else '',
                            url=item.get('url', ''),
                            source=item.get('publisher', {}).get('title', 'Unknown'),
                            published_date=item.get('published date', datetime.now().isoformat()),
                        )
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Failed to fetch news for query '{query}': {e}")
                    # Fallback to general news if query fails
                    articles = self._fetch_from_gnews()
            else:
                articles = self._fetch_from_gnews()
        
        # If gnews failed completely (articles is empty), use hardcoded fallback
        if not articles:
             articles = self._get_fallback_news()
        
        # Cache ONLY if it's the general feed
        if not query and articles:
            self._save_cache(articles)
        
        return articles[:5]
    
    def get_news(self, query: str = None) -> List[Dict]:
        """Alias for fetch_news to match API expected by app.py"""
        articles = self.fetch_news(query=query)
        return [asdict(a) for a in articles]
    
    def _fetch_from_gnews(self) -> List[NewsArticle]:
        """Fetch news using gnews library"""
        articles = []
        
        for keyword in self.LEGAL_KEYWORDS[:5]:  # Limit to avoid rate limiting
            try:
                news_items = self._gnews.get_news(keyword)
                
                for item in news_items[:3]:  # Top 3 per keyword
                    article = NewsArticle(
                        title=item.get('title', ''),
                        summary=item.get('description', '')[:200] if item.get('description') else '',
                        url=item.get('url', ''),
                        source=item.get('publisher', {}).get('title', 'Unknown'),
                        published_date=item.get('published date', datetime.now().isoformat()),
                    )
                    
                    # Avoid duplicates
                    if not any(a.title == article.title for a in articles):
                        articles.append(article)
                        
            except Exception as e:
                logger.warning(f"Failed to fetch news for '{keyword}': {e}")
        
        logger.info(f"Fetched {len(articles)} articles from GNews")
        return articles
    
    def _get_fallback_news(self) -> List[NewsArticle]:
        """Return placeholder news when gnews is unavailable"""
        now = datetime.now().isoformat()
        
        return [
            NewsArticle(
                title="Supreme Court Rules on Right to Privacy in Digital Age",
                summary="The apex court delivered a landmark judgment expanding the scope of Article 21 to include digital privacy rights...",
                url="https://www.livelaw.in/top-stories",
                source="LiveLaw",
                published_date=now,
                is_fallback=True
            ),
            NewsArticle(
                title="New Bail Guidelines Issued by Delhi High Court",
                summary="The court has laid down comprehensive guidelines for expeditious disposal of bail applications in criminal matters...",
                url="https://www.barandbench.com/news",
                source="Bar & Bench",
                published_date=now,
                is_fallback=True
            ),
            NewsArticle(
                title="BNS Implementation: Key Changes from IPC",
                summary="A detailed analysis of major changes in the Bharatiya Nyaya Sanhita replacing the Indian Penal Code...",
                url="https://www.scconline.com/blog/",
                source="SCC Online",
                published_date=now,
                is_fallback=True
            ),
            NewsArticle(
                title="Legal Aid Services Expanded Across States",
                summary="National Legal Services Authority announces expansion of free legal aid coverage to include more citizens...",
                url="https://www.indialegallive.com/",
                source="India Legal",
                published_date=now,
                is_fallback=True
            ),
            NewsArticle(
                title="Anticipatory Bail: Recent Developments in Jurisprudence",
                summary="Analysis of recent High Court and Supreme Court decisions on anticipatory bail under Section 438 CrPC...",
                url="https://www.scobserver.in/",
                source="Supreme Court Observer",
                published_date=now,
                is_fallback=True
            ),
        ]
    
    def _load_cache(self) -> Optional[List[NewsArticle]]:
        """Load cached news from JSON file"""
        try:
            if self.cache_path.exists():
                # Check if cache is less than 24 hours old
                mtime = datetime.fromtimestamp(self.cache_path.stat().st_mtime)
                age_hours = (datetime.now() - mtime).total_seconds() / 3600
                
                if age_hours < 24:
                    with open(self.cache_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return [NewsArticle(**article) for article in data.get('articles', [])]
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
        
        return None
    
    def _save_cache(self, articles: List[NewsArticle]) -> None:
        """Save news to JSON cache"""
        try:
            data = {
                'fetched_at': datetime.now().isoformat(),
                'articles': [asdict(a) for a in articles]
            }
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Cached {len(articles)} articles to {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def get_articles_dict(self) -> Dict:
        """Get articles as dictionary for API response"""
        articles = self.fetch_news()
        return {
            'articles': [asdict(a) for a in articles],
            'count': len(articles),
            'source': 'gnews' if self._gnews else 'fallback'
        }


# Create a singleton instance
_scraper_instance = None

def get_news_scraper() -> LegalNewsScraper:
    """Get or create the news scraper singleton"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = LegalNewsScraper()
    return _scraper_instance
