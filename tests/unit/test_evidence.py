import pytest
from retrieval.models import SearchResult, Provenance, AuthorityLevel, EvidenceSet
from retrieval.evidence import EvidenceValidator

def test_evidence_model_provenance():
    # Test optional fields
    prov = Provenance()
    assert prov.source_authority == AuthorityLevel.UNKNOWN
    assert prov.source_date is None
    
    # Test full provenance
    prov_full = Provenance(
        source_authority=AuthorityLevel.PRIMARY_OFFICIAL,
        source_date="2024-01-01",
        effective_from="2024-07-01",
        effective_until=None
    )
    
    result = SearchResult(
        chunk_id="test_1",
        text="Sample law text",
        score=0.9,
        law_type="IPC",
        section_number="IPC_302",
        source_dataset="ipc.csv",
        dataset_type="statutory",
        metadata={},
        provenance=prov_full
    )
    
    assert result.provenance.source_authority == AuthorityLevel.PRIMARY_OFFICIAL

def test_deduplication():
    validator = EvidenceValidator()
    
    prov1 = Provenance(source_authority=AuthorityLevel.PRIMARY_OFFICIAL)
    prov2 = Provenance(source_authority=AuthorityLevel.SECONDARY_LEGAL)
    
    res1 = SearchResult("1", "Text", 0.9, "IPC", "302", "d1", "statutory", {}, prov1)
    res2 = SearchResult("1", "Text", 0.8, "IPC", "302", "d1", "statutory", {}, prov1) # Exact duplicate
    res3 = SearchResult("1", "Text", 0.7, "IPC", "302", "d1", "statutory", {}, prov2) # Different provenance
    
    evidence = EvidenceSet(statutory_results=[res1, res2, res3])
    
    validated = validator.validate(evidence)
    
    # res1 and res2 are duplicates, res3 has different provenance so it's kept
    assert len(validated.statutory_results) == 2
    assert validated.validation_metadata["statutory"]["duplicates_removed"] == 1
    
    auth_levels = {r.provenance.source_authority for r in validated.statutory_results}
    assert AuthorityLevel.PRIMARY_OFFICIAL in auth_levels
    assert AuthorityLevel.SECONDARY_LEGAL in auth_levels

def test_provenance_validation_missing():
    validator = EvidenceValidator()
    
    res = SearchResult("1", "Text", 0.9, "IPC", "302", "d1", "statutory", {})
    evidence = EvidenceSet(statutory_results=[res])
    
    validated = validator.validate(evidence)
    
    assert len(validated.statutory_results) == 1
    assert validated.validation_metadata["statutory"]["missing_provenance_count"] == 1
    assert validated.statutory_results[0].provenance is not None
    assert validated.statutory_results[0].provenance.source_authority == AuthorityLevel.UNKNOWN

def test_conflict_preservation():
    validator = EvidenceValidator()
    
    # Same chunk_id, different text (conflict)
    res1 = SearchResult("1", "Text A", 0.9, "IPC", "302", "d1", "statutory", {})
    res2 = SearchResult("1", "Text B", 0.8, "IPC", "302", "d1", "statutory", {})
    
    evidence = EvidenceSet(statutory_results=[res1, res2])
    
    validated = validator.validate(evidence)
    
    # Validator should not discard conflicts
    assert len(validated.statutory_results) == 2
