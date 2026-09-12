import pytest
from unittest.mock import MagicMock, patch
from retrieval.pipeline import RetrievalPipeline
from retrieval.models import SearchResult
from agents.query_classifier import QueryType

@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.statutory_index = True
    store.case_law_index = True
    return store

@pytest.fixture
def mock_reranker():
    return MagicMock()

@pytest.fixture
def pipeline(mock_vector_store, mock_reranker):
    return RetrievalPipeline(vector_store=mock_vector_store, reranker=mock_reranker)

def test_empty_retrieval(pipeline, mock_vector_store):
    mock_vector_store.hybrid_search_statutory.return_value = []
    
    evidence = pipeline.run(
        query="empty query",
        enhanced_query="empty query",
        query_type=QueryType.LEGAL_INFO,
        extracted_sections=[],
        extracted_law_types=[]
    )
    
    assert len(evidence.statutory_results) == 0
    assert len(evidence.case_law_results) == 0

def test_statutory_retrieval_and_reranking(pipeline, mock_vector_store, mock_reranker):
    mock_statutory_results = [
        SearchResult(chunk_id="1", text="statute 1", score=0.8, law_type="IPC", section_number="302", source_dataset="ipc", dataset_type="statutory", metadata={})
    ]
    mock_vector_store.hybrid_search_statutory.return_value = mock_statutory_results
    
    mock_reranked_results = [
        SearchResult(chunk_id="1", text="statute 1", score=0.9, law_type="IPC", section_number="302", source_dataset="ipc", dataset_type="statutory", metadata={})
    ]
    mock_reranker.rerank.return_value = mock_reranked_results
    
    evidence = pipeline.run(
        query="murder",
        enhanced_query="murder",
        query_type=QueryType.LEGAL_INFO,
        extracted_sections=["302"],
        extracted_law_types=["IPC"]
    )
    
    # Verify vector store called correctly
    mock_vector_store.hybrid_search_statutory.assert_called_once()
    
    # Verify reranker called correctly with 'precision' mode due to sections
    mock_reranker.rerank.assert_called_once()
    args, kwargs = mock_reranker.rerank.call_args
    assert kwargs['mode'] == 'precision'
    assert kwargs['requested_sections'] == ["302"]
    
    assert evidence.statutory_results == mock_reranked_results
    assert len(evidence.case_law_results) == 0

def test_case_law_retrieval_for_bail(pipeline, mock_vector_store, mock_reranker):
    mock_stat_results = [
        SearchResult(chunk_id="1", text="bail statute", score=0.8, law_type="CrPC", section_number="437", source_dataset="crpc", dataset_type="statutory", metadata={})
    ]
    mock_vector_store.hybrid_search_statutory.return_value = mock_stat_results
    mock_reranker.rerank.side_effect = [
        mock_stat_results,  # First call (statutory)
        [SearchResult(chunk_id="c1", text="bail case", score=0.85, law_type="case", section_number="", source_dataset="sc", dataset_type="case_law", metadata={})]  # Second call (case law)
    ]
    
    mock_vector_store.search_case_law.return_value = [
        SearchResult(chunk_id="c1", text="bail case", score=0.7, law_type="case", section_number="", source_dataset="sc", dataset_type="case_law", metadata={})
    ]
    
    evidence = pipeline.run(
        query="bail conditions",
        enhanced_query="bail conditions",
        query_type=QueryType.BAIL_QUERY,
        extracted_sections=[],
        extracted_law_types=[]
    )
    
    mock_vector_store.search_case_law.assert_called_once()
    assert len(evidence.case_law_results) == 1
    assert evidence.case_law_results[0].chunk_id == "c1"

@patch('retrieval.pipeline.session_manager')
def test_session_documents(mock_session_manager, pipeline, mock_vector_store):
    mock_session = MagicMock()
    mock_session.documents = {"doc1.pdf"}
    
    mock_doc_result = MagicMock()
    mock_doc_result.filename = "doc1.pdf"
    mock_doc_result.text = "user text"
    mock_doc_result.document_type = "pdf"
    mock_doc_result.score = 0.95
    
    mock_session.search.return_value = [mock_doc_result]
    mock_session_manager.get_session.return_value = mock_session
    
    mock_vector_store.hybrid_search_statutory.return_value = []
    
    evidence = pipeline.run(
        query="my document",
        enhanced_query="my document",
        query_type=QueryType.LEGAL_INFO,
        extracted_sections=[],
        extracted_law_types=[],
        session_id="test_session"
    )
    
    mock_session_manager.get_session.assert_called_with("test_session")
    assert len(evidence.session_documents) == 1
    assert evidence.session_documents[0]["filename"] == "doc1.pdf"
    assert evidence.session_documents[0]["text"] == "user text"
