import pytest
from unittest.mock import patch

@pytest.fixture
def mock_vector_store():
    with patch('vector_store.VectorStore.load') as mock_load, \
         patch('vector_store.VectorStore.hybrid_search_statutory') as mock_search_stat, \
         patch('vector_store.VectorStore.search_case_law') as mock_search_case_law, \
         patch('vector_store.VectorStore.search_bail') as mock_search_bail:
        
        mock_load.return_value = None
        
        from reranker import SearchResult
        
        statutory_results = [
            SearchResult(
                chunk_id="stat_1",
                text="Trespassing on burial places offering indignity to human corpse.",
                score=0.9,
                law_type="IPC",
                section_number="IPC_297",
                source_dataset="ipc",
                dataset_type="statutory",
                metadata={"title": "Section 297", "chapter": "15", "section_boost": 0.0}
            ),
            SearchResult(
                chunk_id="stat_2",
                text="Another section text.",
                score=0.5,
                law_type="IPC",
                section_number="IPC_298",
                source_dataset="ipc",
                dataset_type="statutory",
                metadata={"title": "Section 298", "chapter": "15", "section_boost": 0.0}
            )
        ]
        
        mock_search_stat.return_value = statutory_results
        mock_search_case_law.return_value = []
        mock_search_bail.return_value = []
        
        yield {
            "load": mock_load,
            "search_statutory": mock_search_stat,
            "search_case_law": mock_search_case_law,
            "search_bail": mock_search_bail,
            "statutory_results": statutory_results
        }

@pytest.fixture
def mock_llm():
    with patch('llm_provider.LLMProvider.generate') as mock_generate:
        # generate returns (response_text, answer_mode, metadata)
        mock_generate.return_value = ("Mocked LLM response.", None, {})
        
        yield {
            "generate": mock_generate
        }

@pytest.fixture
def mock_kanoon():
    with patch('services.indian_kanoon.IndianKanoonAPI.search') as mock_search:
        from services.indian_kanoon import KanoonSearchResult, KanoonDocument
        
        mock_search.return_value = KanoonSearchResult(
            documents=[
                KanoonDocument(
                    title="Mock Case",
                    url="http://mock",
                    date="2023",
                    court="Mock Court",
                    snippet="Mock snippet",
                    citation="Mock citation"
                )
            ],
            total_results=1,
            time_taken=0.1
        )
        yield mock_search

@pytest.fixture
def mock_lifespan_dependencies(mock_vector_store, mock_llm):
    """
    Use this fixture for API smoke tests to mock out expensive lifespan dependencies.
    """
    with patch('reranker.LegalReranker.__init__', return_value=None), \
         patch('agents.crew_orchestrator.JustiAssistCrew.__init__', return_value=None):
        yield
