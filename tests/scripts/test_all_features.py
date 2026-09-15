import asyncio
import os
import sys

async def main():
    print("Loading JustiAssist...")
    from app import (
        query_classifier, query_reformulator, bail_evaluator, feedback_evaluator,
        reranker, context_builder, confidence_scorer, crew_orchestrator, vector_store
    )
    from vector_store import VectorStore
    from agents.orchestrator import AgentOrchestrator
    
    vs = VectorStore()
    vs.load()
    
    from reranker import LegalReranker
    from context_builder import ContextBuilder
    from confidence_scorer import ConfidenceScorer
    
    rerank = LegalReranker(mode='balanced')
    cb = ContextBuilder()
    cs = ConfidenceScorer()
    
    from types import SimpleNamespace
    deps = SimpleNamespace(vector_store=vs, reranker=rerank)
    
    deps.agent_orchestrator = AgentOrchestrator(
        vector_store=deps.vector_store,
        reranker=deps.reranker
    )
    print("AgentOrchestrator Initialized")
    crew = deps.agent_orchestrator
    
    print("="*50)
    
    query = "Tell me about BNS 304"
    result = None
    
    class MockSession:
        async def process_query(self, query):
            print(f"Processing: {query}")
            from agents.crew_orchestrator import CrewResult
            from agents.query_classifier import QueryType
            result = CrewResult(query=query, query_type=QueryType.LEGAL_INFO)
            # Just do a quick run to see if it errors out
            try:
                # Mock process
                result = await crew.process_query(query)
                print("Crew orchestration ran without errors.")
                print("Crew orchestration ran without errors.")
                return True
            except Exception as e:
                print(f"Error in crew orchestration: {e}")
                import traceback
                traceback.print_exc()
                return False
                
    session = MockSession()
    success = await session.process_query(query)
    
    print("\n" + "="*50)
    print("TESTING FIRECRAWL (Webintel)")
    print("="*50)
    
    from firecrawl import FirecrawlApp
    try:
        from config import settings
        app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY.get_secret_value() if settings.FIRECRAWL_API_KEY else "")
        results = app.search(query=f"India law legal BNS 304", limit=2)
        print(f"Firecrawl returned data successfully.")
        
        # Test LegalNewsScraper as well
        print("\n" + "="*50)
        print("TESTING NEWS SCRAPER")
        print("="*50)
        from services.news_scraper import get_news_scraper
        scraper = get_news_scraper()
        news = scraper.fetch_news(limit=2) if hasattr(scraper, 'fetch_news') else []
        print(f"News Scraper returned {len(news)} items.")
        
    except Exception as e:
        print(f"Firecrawl error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
