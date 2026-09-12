import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_app_module():
    with patch('app.VectorStore') as mock_vs, \
         patch('app.LegalReranker') as mock_rr, \
         patch('app.ContextBuilder') as mock_cb, \
         patch('retrieval.pipeline.RetrievalPipeline') as mock_rp:
        yield mock_vs, mock_rr, mock_cb, mock_rp

@pytest.mark.asyncio
async def test_retrieval_pipeline_wiring():
    with patch('app.VectorStore') as mock_vs_class, \
         patch('app.LegalReranker') as mock_rr_class, \
         patch('app.ContextBuilder') as mock_cb_class, \
         patch('app.ConfidenceScorer') as mock_cs_class, \
         patch('retrieval.pipeline.RetrievalPipeline') as mock_rp_class, \
         patch('app.JustiAssistCrew') as mock_crew_class, \
         patch('app.VECTOR_STORE_PATH') as mock_path, \
         patch('services.database.init_db'):
        
        mock_path.exists.return_value = False
        
        # Mock instance returned by VectorStore()
        mock_vs_instance = MagicMock()
        mock_vs_class.return_value = mock_vs_instance
        
        mock_rr_instance = MagicMock()
        mock_rr_class.return_value = mock_rr_instance
        
        import app
        from core.dependencies import deps
        
        # Run app initialization (async context manager)
        async with app.lifespan(None):
            # Verify RetrievalPipeline was instantiated with the correctly loaded vector store
            mock_rp_class.assert_called_once_with(
                vector_store=mock_vs_instance,
                reranker=mock_rr_instance
            )
            
            # Verify Crew Orchestrator received the pipeline
            mock_crew_class.assert_called_once()
            _, kwargs = mock_crew_class.call_args
            assert kwargs['retrieval_pipeline'] == deps.retrieval_pipeline
            assert kwargs['vector_store'] == mock_vs_instance

