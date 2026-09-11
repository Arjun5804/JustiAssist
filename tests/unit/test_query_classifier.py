import pytest
from unittest.mock import patch, AsyncMock
from agents.query_classifier import QueryClassifier, QueryType

@pytest.fixture
def patch_call_llm():
    with patch('agents.query_classifier.call_llm', new_callable=AsyncMock) as mock:
        yield mock

@pytest.mark.asyncio
async def test_classifier_statutory(patch_call_llm):
    # Mock LLM response for legal info
    patch_call_llm.return_value = '{"type": "LEGAL_INFO", "confidence": 0.95, "reason": "test"}'
    
    classifier = QueryClassifier()
    result = await classifier.classify("What is IPC 302?")
    
    assert result.query_type == QueryType.LEGAL_INFO
    assert patch_call_llm.called

@pytest.mark.asyncio
async def test_classifier_bail(patch_call_llm):
    patch_call_llm.return_value = '{"type": "BAIL_QUERY", "confidence": 0.9, "reason": "test"}'
    
    classifier = QueryClassifier()
    result = await classifier.classify("My friend was arrested, how to get bail")
    
    assert result.query_type == QueryType.BAIL_QUERY

@pytest.mark.asyncio
async def test_classifier_document(patch_call_llm):
    patch_call_llm.return_value = '{"type": "DOCUMENT_QUERY", "confidence": 0.9, "reason": "test"}'
    
    classifier = QueryClassifier()
    result = await classifier.classify("Summarize this document")
    
    assert result.query_type == QueryType.DOCUMENT_QUERY

@pytest.mark.asyncio
async def test_classifier_fallback(patch_call_llm):
    # If LLM fails, should fallback to heuristics
    patch_call_llm.side_effect = Exception("API Error")
    
    classifier = QueryClassifier()
    
    # Test bail fallback
    result1 = await classifier.classify("need anticipatory bail")
    assert result1.query_type == QueryType.BAIL_QUERY
    
    # Test document fallback
    result2 = await classifier.classify("summarize this pdf file")
    assert result2.query_type == QueryType.DOCUMENT_QUERY
    
    # Test default fallback
    result3 = await classifier.classify("random query without keywords")
    assert result3.query_type == QueryType.LEGAL_INFO
