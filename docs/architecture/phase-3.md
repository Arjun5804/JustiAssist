# Phase 3: Evidence & Grounding Foundation

## Objective
Establish the data contracts and validation layers for evidence provenance, temporal metadata, authority, and claim mapping, creating a solid foundation for future grounding and verification pipelines.

## Changes Made
1. **Canonical Evidence Model Update:** Expanded `SearchResult` in `retrieval/models.py` to include a `Provenance` dataclass, supporting `source_authority` (based on `AuthorityLevel`), `source_date`, `effective_from`, and `effective_until`. 
2. **Authority Classification:** Introduced `AuthorityLevel` containing explicit levels like `PRIMARY_OFFICIAL`, `TRUSTED_LEGAL`, `SECONDARY_LEGAL`, `NEWS`, and `UNKNOWN`.
3. **Evidence Validation Layer:** Created `retrieval/evidence.py` with an `EvidenceValidator` to deduplicate results without losing provenance, handle missing provenance defaults, and ensure contradictory evidence is correctly preserved rather than silently dropped.
4. **Data Contract (ValidatedEvidenceSet & Claim):** Created `ValidatedEvidenceSet` as the core contract between retrieval and ContextBuilder. Added `Claim` to model the output of generation (claim text -> evidence IDs).
5. **ContextBuilder Mapping:** Updated `context_builder.py` to preserve a machine-readable mapping between the generated formatted text chunks and the actual underlying `SearchResult` containing provenance. This mapping enables downstream citation/claim verification logic.
6. **Integration:** Integrated `EvidenceValidator` into `api/query.py`'s standard pipeline.

## Files Changed
*   `retrieval/models.py`: Added models `AuthorityLevel`, `Provenance`, `ValidatedEvidenceSet`, `Claim`.
*   `retrieval/evidence.py` (New): Added `EvidenceValidator`.
*   `api/query.py`: Integrated `EvidenceValidator` into the pipeline.
*   `context_builder.py`: Modified to return a mapping along with the context.
*   `tests/unit/test_context_builder.py`: Updated to handle new return tuple.
*   `tests/unit/test_evidence.py` (New): Tests for validation layer.
*   `docs/architecture/evidence-model.md` (New): Architectural documentation of the evidence model.

## Architectural Impact
The architectural boundary is now clearly defined as:
`RetrievalPipeline -> EvidenceSet -> EvidenceValidator -> ValidatedEvidenceSet -> ContextBuilder`

The new mapping from ContextBuilder enables future phases to accurately trace generated facts back to their source chunks and their exact provenance, forming the bedrock of claim verification.

## Tests Executed
*   Command: `python -m pytest tests/`
*   Results: 37 passed, 4 warnings in ~18s.
*   New Tests: `test_evidence_model_provenance`, `test_deduplication`, `test_provenance_validation_missing`, `test_conflict_preservation`. All passing.

## Known Limitations & Out of Scope
*   **No Resolution of Legal Truth:** The validator deliberately does not try to figure out which of two contradictory pieces of evidence is the "correct" legal truth; this is left for downstream verification layers.
*   **No LLM Claim Verification:** We have the data contract (`Claim`) but have not built the LLM pipeline to automatically produce these claims.
*   **No Temporal Applicability Logic:** We store `effective_from`/`until` but do not yet use it to filter out superseded laws dynamically.

This phase deliberately focused on the deterministic data structures and strict provenance constraints rather than the intelligent verification engine itself.
