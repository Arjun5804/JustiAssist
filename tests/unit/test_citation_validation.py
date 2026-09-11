import pytest
from citation_validator import CitationValidator

def test_valid_citations():
    validator = CitationValidator()
    
    response = "According to Section 302, murder is punishable. Also IPC 300 defines it."
    context_chunks = [
        {"section_number": "IPC_302", "text": "Punishment for murder."},
        {"section_number": "IPC_300", "text": "Definition of murder."}
    ]
    
    val = validator.validate(response, context_chunks)
    assert val.is_valid is True
    assert val.fabrication_score == 0.0
    assert len(val.invalid_sections) == 0

def test_missing_citations_in_response():
    validator = CitationValidator()
    
    # Response has no citations
    response = "Murder is a crime. It is punishable."
    context_chunks = [
        {"section_number": "IPC_302", "text": "Punishment for murder."}
    ]
    
    val = validator.validate(response, context_chunks)
    assert val.is_valid is True
    assert val.fabrication_score == 0.0
    assert len(val.cited_sections) == 0

def test_invalid_evidence_reference():
    validator = CitationValidator()
    
    # Response cites Section 420, but context only has 302
    response = "According to Section 420, cheating is a crime."
    context_chunks = [
        {"section_number": "IPC_302", "text": "Punishment for murder."}
    ]
    
    val = validator.validate(response, context_chunks)
    # 1 citation, 0 valid -> 100% fabricated
    assert val.is_valid is False
    assert val.fabrication_score == 1.0
    assert len(val.invalid_sections) > 0

def test_malformed_citations():
    validator = CitationValidator()
    
    # Should still extract numbers from messy formatting
    response = "As per Sec. 302 and article 21(A)"
    context_chunks = [
        {"section_number": "IPC_302", "text": "Punishment for murder."},
        {"section_number": "Const_21A", "text": "Education."}
    ]
    
    val = validator.validate(response, context_chunks)
    assert val.is_valid is True
    assert val.fabrication_score == 0.0

def test_empty_evidence_or_answer():
    validator = CitationValidator()
    
    val1 = validator.validate("", [{"section_number": "123"}])
    assert val1.is_valid is True
    
    val2 = validator.validate("Section 123", [])
    assert val2.is_valid is False
    assert val2.fabrication_score == 1.0
