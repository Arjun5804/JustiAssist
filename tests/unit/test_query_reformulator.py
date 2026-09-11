from agents.query_reformulator import QueryReformulator

def test_reformulate_basic():
    reformulator = QueryReformulator()
    result = reformulator.reformulate("What is IPC 302?")
    
    assert "IPC 302" in result.original_query
    assert "IPC_302" in result.extracted_sections
    assert "IPC" in result.extracted_law_types
    assert "Indian Penal Code" in result.enhanced_query

def test_reformulate_bail():
    reformulator = QueryReformulator()
    result = reformulator.for_bail_query("anticipatory bail under CrPC 438")
    
    assert "anticipatory bail" in result.enhanced_query.lower()
    assert "CrPC_438" in result.extracted_sections
    assert "CrPC" in result.extracted_law_types
    assert "bail provisions" in result.enhanced_query

def test_reformulate_synonyms():
    reformulator = QueryReformulator()
    result = reformulator.reformulate("punishment for theft")
    
    # "theft" has synonyms in SYNONYMS like "stealing", "larceny"
    # "punishment" has synonyms like "penalty"
    assert "stealing" in result.enhanced_query.lower() or "larceny" in result.enhanced_query.lower()
    assert "penalty" in result.enhanced_query.lower() or "sentence" in result.enhanced_query.lower()

def test_reformulate_no_keywords():
    reformulator = QueryReformulator()
    result = reformulator.reformulate("hello world")
    
    assert result.original_query == "hello world"
    assert len(result.extracted_sections) == 0
    assert len(result.extracted_law_types) == 0
