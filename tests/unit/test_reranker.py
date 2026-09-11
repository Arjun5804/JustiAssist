from reranker import LegalReranker, SearchResult

def test_reranker_statute_presence():
    reranker = LegalReranker(mode='balanced')
    
    res_with_statute = SearchResult(
        chunk_id="1", text="Section 302 of IPC deals with murder.", score=0.5,
        law_type="IPC", section_number="", source_dataset="", dataset_type="", metadata={}
    )
    res_no_statute = SearchResult(
        chunk_id="2", text="Just talking about crimes.", score=0.5,
        law_type="IPC", section_number="", source_dataset="", dataset_type="", metadata={}
    )
    
    results = reranker.rerank([res_with_statute, res_no_statute], requested_sections=[])
    
    # The one with the statute should be ranked higher
    assert results[0].chunk_id == "1"

def test_reranker_section_match():
    reranker = LegalReranker(mode='balanced')
    
    res_match = SearchResult(
        chunk_id="1", text="Text", score=0.5,
        law_type="IPC", section_number="IPC_302", source_dataset="", dataset_type="", metadata={}
    )
    res_no_match = SearchResult(
        chunk_id="2", text="Text", score=0.5,
        law_type="IPC", section_number="IPC_379", source_dataset="", dataset_type="", metadata={}
    )
    
    results = reranker.rerank([res_match, res_no_match], requested_sections=["IPC_302"])
    
    assert results[0].chunk_id == "1"
    
def test_reranker_entity_density():
    reranker = LegalReranker(mode='balanced')
    
    text_high_density = "Supreme Court ruled in 2014 SCC 123 that High Court learned judge erred."
    res_high = SearchResult(
        chunk_id="1", text=text_high_density, score=0.5,
        law_type="", section_number="", source_dataset="", dataset_type="", metadata={}
    )
    
    text_low = "Normal text without courts." * 10
    res_low = SearchResult(
        chunk_id="2", text=text_low, score=0.5,
        law_type="", section_number="", source_dataset="", dataset_type="", metadata={}
    )
    
    results = reranker.rerank([res_high, res_low], requested_sections=[])
    
    assert results[0].chunk_id == "1"
