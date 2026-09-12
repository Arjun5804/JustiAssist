"""
Temporary dependency container to safely extract routes from app.py.
This holds references to global services initialized during app lifespan.
"""

from typing import Optional

class DepsContainer:
    def __init__(self):
        # Core RAG
        self.vector_store = None
        self.reranker = None
        self.context_builder = None
        self.confidence_scorer = None
        self.llm_provider = None
        self.retrieval_pipeline = None
        
        # Agents (Legacy / Utility)
        self.query_classifier = None
        self.query_reformulator = None
        self.bail_evaluator = None
        self.feedback_evaluator = None
        
        # Orchestrator (v2)
        self.crew_orchestrator = None

# Global dependency instance
deps = DepsContainer()
