# JustiAssist — Phase 2 Architecture: Retrieval Pipeline Unification

## Overview

In Phase 2, the primary goal was to unify and modularize the fragmented retrieval paths across JustiAssist. Previously, `api/query.py` and `agents/crew_orchestrator.py` contained identical, ~100-line inline retrieval orchestrations that handled vector searches, reranking, and session document retrieval. 

This phase established a **Canonical Retrieval Pipeline** without altering the underlying core algorithms (FAISS, BM25, LegalReranker) or their configuration (e.g., top-k, fusion weights).

## Changes Implemented

### 1. `retrieval` Package and Canonical Models
- Created `retrieval/__init__.py`, `retrieval/models.py`, and `retrieval/pipeline.py`.
- **`SearchResult`**: Unified the previously conflicting `SearchResult` definitions from `vector_store.py` and `reranker.py` into a single, canonical `retrieval.models.SearchResult` dataclass.
- **`EvidenceSet`**: Introduced a new strongly-typed result model to encapsulate `statutory_results`, `case_law_results`, and `session_documents`.

### 2. The `RetrievalPipeline`
- Implemented `RetrievalPipeline.run(...)` which orchestrates:
  1. Session Document retrieval.
  2. Statutory Hybrid Search (`vector_store.hybrid_search_statutory`).
  3. Statutory Reranking (`reranker.rerank` with 'precision' or 'balanced' modes).
  4. Case Law Retrieval (if `BAIL_QUERY`).
  5. Case Law Reranking (with 'recall' mode).
- **Separation of Concerns**: The pipeline is strictly responsible for *retrieval* and returns an `EvidenceSet`. It does not construct LLM prompts or interact with `ContextBuilder`, keeping the context stringification strictly in the orchestration layer.

### 3. Migration
- **`agents/crew_orchestrator.py`**: Replaced the duplicate Stage 3 retrieval sequence with a call to `RetrievalPipeline`.
- **`api/query.py`**: Replaced the legacy and streaming retrieval orchestration logic with `RetrievalPipeline`, while preserving event emission schemas.
- **Dead Code Cleanup**: Deleted `agents/tools/` which contained unused CrewAI wrappers that were incompatible with Python 3.14.

### 4. Testing
- Created `tests/unit/test_retrieval_pipeline.py` with mock-based unit tests for:
  - Empty queries
  - Statutory retrieval & precision reranking
  - Bail queries (case law fallback)
  - Session document retrieval
- Verified all unit (`pytest -q`) and integration tests (`pytest -q -m integration`) passed successfully.

## Future Recommendations
Currently, `vector_store.py`, `reranker.py`, and `context_builder.py` remain in the root directory. Now that the canonical abstraction exists and works, a future Phase (or cleanup task) should physically move these implementations under the `retrieval/` package to finalize module encapsulation.
