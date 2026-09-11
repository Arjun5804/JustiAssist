import pytest
from context_builder import ContextBuilder
from dataclasses import dataclass

@dataclass
class MockResult:
    law_type: str
    section_number: str
    text: str
    source_dataset: str
    dataset_type: str
    score: float
    metadata: dict

def test_context_builder_grouping():
    builder = ContextBuilder()
    
    statutory = [
        MockResult("IPC", "IPC_302", "Text 302", "ipc.csv", "statutory", 0.9, {})
    ]
    case_law = [
        MockResult("Other", "SC_123", "Supreme Court case", "sc.csv", "case_law", 0.8, {})
    ]
    
    context = builder.build_structured_context(statutory_results=statutory, case_law_results=case_law)
    
    assert "STATUTORY PROVISIONS: IPC" in context
    assert "CASE LAW PRECEDENTS: Supreme Court" in context
    assert "IPC_302" in context
    assert "SC_123" in context

def test_context_builder_contradictions():
    builder = ContextBuilder()
    
    statutory = [
        MockResult("IPC", "IPC_302", "Punished with 10 years", "ipc.csv", "statutory", 0.9, {}),
        MockResult("IPC", "IPC_302", "Punished with 14 years", "ipc.csv", "statutory", 0.8, {})
    ]
    
    context = builder.build_structured_context(statutory_results=statutory)
    
    assert "CRITICAL CONTRADICTION WARNINGS" in context
    assert "Conflicting punishment terms" in context

def test_context_builder_empty():
    builder = ContextBuilder()
    
    context = builder.build_structured_context([], [])
    assert "No relevant legal context found." in context
