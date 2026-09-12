# JustiAssist Evidence Model Architecture

This document describes the canonical representation of retrieved legal evidence, its provenance, and how it is validated before generation.

## 1. Canonical Evidence Model

The core representation of retrieved evidence is the `SearchResult` defined in `retrieval/models.py`.

```python
@dataclass
class SearchResult:
    chunk_id: str
    text: str
    score: float
    law_type: str
    section_number: str
    source_dataset: str
    dataset_type: str
    metadata: Dict[str, Any]
    provenance: Optional[Provenance] = None
```

All retrieval mechanisms (hybrid statutory, case law) produce instances of `SearchResult`. We do not maintain competing evidence structures.

## 2. Provenance and Authority

The `Provenance` object represents the origin and authority level of the evidence, completely separate from its internal database identity.

```python
@dataclass
class Provenance:
    source_authority: AuthorityLevel = AuthorityLevel.UNKNOWN
    source_date: Optional[str] = None
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
```

### Authority Levels

Sources are categorized to help downstream components weight their legal significance:
*   `PRIMARY_OFFICIAL`: Official legislation, gazettes, Supreme/High Court judgments.
*   `TRUSTED_LEGAL`: Verified legal databases (e.g., Indian Kanoon).
*   `SECONDARY_LEGAL`: Law firm commentary, academic articles.
*   `NEWS`: News publications.
*   `UNKNOWN`: Authority has not been established. This is never treated as a trusted source.

## 3. Evidence Validation Layer

Before evidence is returned by the canonical `RetrievalPipeline`, it is validated by the `EvidenceValidator` (`retrieval/evidence.py`). The pipeline directly returns a `ValidatedEvidenceSet`.

Responsibilities:
*   **Deduplication:** Removes exact duplicates (same text and provenance) regardless of internal chunk_id differences.
*   **ID Validation:** Explicitly checks and requires canonical `chunk_id`. Missing/invalid IDs cause the item to be deterministically rejected.
*   **Conflict Preservation:** If two items contain the same text but have materially different provenance (e.g. from a different database), both are preserved. Contradictions are not resolved at this stage.
*   **Provenance Fallback:** Missing provenance is gracefully filled with `UNKNOWN` defaults without mutating the original retrieved structures and without fabricating legal dates.
*   **Contract:** The validator outputs a `ValidatedEvidenceSet`, solidifying the evidence contract before context generation.

## 4. Claim to Evidence Mapping (The Contract)

The system establishes the foundation for mapping generative claims back to specific evidence chunks without relying on LLMs at this stage.

*   `ContextBuilder` assigns deterministic mapping IDs to evidence and preserves this mapping.
*   A `Claim` model exists to formally link generated text to a list of `evidence_ids`.
*   Later phases (e.g. Claim Verification) will use this contract to validate citations against the preserved evidence IDs and provenance metadata.

## 5. Temporal Metadata

The model includes `effective_from` and `effective_until` to support future reasoning over legal transitions (e.g., IPC to BNS). Currently, these fields are populated only when explicit data is provided; no rules-based inference is performed during validation.

## 6. Out of Scope

This architecture explicitly excludes:
*   Full temporal legal reasoning (inferring transition applicability based on case dates).
*   LLM-based claim verification or contradiction resolution.
*   Adjustments to the underlying FAISS/BM25 retrieval mechanisms.
