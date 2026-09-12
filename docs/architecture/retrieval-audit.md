# JustiAssist — Retrieval Architecture Audit

> **Phase 2** | Generated during retrieval pipeline unification

---

## 1. Overview

The JustiAssist retrieval architecture is currently fragmented. While the core algorithms (FAISS, BM25, Reranker) are robust, their orchestration is duplicated across multiple entry points, making changes risky and tests brittle.

The goal of this audit is to identify all existing retrieval paths, document their behavior, and propose a canonical retrieval pipeline.

---

## 2. Core Retrieval Components Discovered

### 2.1 `VectorStore` (`vector_store.py`)
- **Engine**: FAISS `IndexFlatIP` (cosine similarity) + `rank_bm25`
- **Indices**: Separate `statutory/` (FAISS + BM25) and `case_law/` (FAISS only)
- **Methods**:
  - `hybrid_search_statutory()`: 0.6 FAISS + 0.4 BM25 reciprocal rank fusion
  - `search_case_law()` / `search_bail()`: Semantic-only FAISS search
- **Data Model**: Returns `SearchResult` objects
- **Direct Callers**: `api/query.py`, `agents/crew_orchestrator.py`, `services/hybrid_retriever.py`, `api/documents.py`, `api/features.py`
- **Issue**: Exposed directly to API routes and agents, coupling high-level logic to low-level FAISS/BM25 internals.

### 2.2 `LegalReranker` (`reranker.py`)
- **Purpose**: Two-stage reranking based on statute presence, section match, entity density, and semantic scores.
- **Data Model**: Receives and returns `SearchResult` (aliased in some places as `RerankSearchResult`).
- **Direct Callers**: `api/query.py` (legacy pipeline), `agents/crew_orchestrator.py` (v2 pipeline).
- **Issue**: Reranking logic is manually wired up after vector search in every calling pipeline.

### 2.3 `ContextBuilder` (`context_builder.py`)
- **Purpose**: Groups retrieved chunks by evidence type (Statutory, Case Law, Uploaded Documents) and law type for injection into LLM prompts.
- **Direct Callers**: `api/query.py`, `agents/crew_orchestrator.py`.
- **Issue**: Manually called in every pipeline immediately after reranking.

### 2.4 `HybridRetriever` (`services/hybrid_retriever.py`)
- **Purpose**: Intended to be a unified retriever that calls local vectors, Indian Kanoon, and News concurrently.
- **Issue**: This is largely **bypassed** by the main pipelines (`api/query.py` and `crew_orchestrator.py`), which reimplement concurrent Kanoon/News fetching inline.
- **Status**: Partially integrated, overlapping responsibility.

### 2.5 `DocumentSession` (`document_session.py`)
- **Purpose**: In-memory FAISS index for uploaded user documents.
- **Methods**: `session.search(query, top_k=5)`
- **Issue**: Search results from this are manually converted to dictionaries and injected into the pipeline separate from statutory/case law results.

### 2.6 CrewAI Tools (`agents/tools/`)
- **Purpose**: Wrappers for VectorSearch, Kanoon, Firecrawl intended for CrewAI agents.
- **Status**: **Dead code.** Python 3.14 incompatibility prevents CrewAI usage. Can be safely ignored/removed.

---

## 3. Retrieval Orchestration Paths (The Duplication)

The most severe issue is the duplication of retrieval orchestration. There are two identical ~200-line implementations of the retrieval flow.

### Path A: Legacy `/query` (in `api/query.py`)
- **Flow**:
  1. `QueryReformulator.reformulate()`
  2. `session_manager.get_session().search()` (if doc session exists)
  3. `VectorStore.hybrid_search_statutory()`
  4. Convert to `RerankSearchResult`
  5. `LegalReranker.rerank(mode='precision'|'balanced')`
  6. (If Bail) `VectorStore.search_case_law()` -> `LegalReranker.rerank(mode='recall')`
  7. `ContextBuilder.build_structured_context()`
- **Status**: Active (used by older UI/tests).

### Path B: v2 Pipeline (in `agents/crew_orchestrator.py`)
- **Flow**:
  - Exactly duplicates the 7 steps from Path A inside the "ResearcherAgent" stage (Stage 3).
- **Status**: Active (used by current React UI via `/api/v2/query`).

---

## 4. The Result Contract Mismatch

Different parts of the code represent retrieved evidence differently:
1. `vector_store.py` -> `SearchResult` dataclass.
2. `reranker.py` -> Requires its own identical `SearchResult` (often aliased to `RerankSearchResult` to avoid collision).
3. `document_session.py` -> Returns raw chunks, which the callers manually convert to `dict` (`{"filename", "text", "is_statutory": False}`).
4. `HybridRetriever` -> Defines `HybridContext`, `KanoonCase`, `NewsItem`.
5. Orchestrators manually convert reranked results to dictionaries for the `ContextBuilder` and citations list.

---

## 5. Canonical Pipeline Recommendation

To resolve the duplication and cleanly separate retrieval from generation, we should implement a **Canonical Retrieval Pipeline**.

### Proposed Module Structure: `retrieval/`
We will create a cohesive `retrieval/` package:
- `models.py`: Unified `SearchResult` (replacing duplicates in `vector_store.py` and `reranker.py`), and `RetrievalContext`.
- `pipeline.py`: The `RetrievalPipeline` orchestrator.

### The Canonical Contract (`RetrievalPipeline`)
```python
class RetrievalPipeline:
    def run(
        self,
        query: str,
        query_type: str,
        reformulated_query: object,
        session_id: str = None
    ) -> RetrievalContext:
        # 1. Retrieve session docs
        # 2. Hybrid search statutory
        # 3. Rerank statutory
        # 4. Search case law (if bail)
        # 5. Rerank case law
        # 6. Return standard evidence object (let generation step build the string context)
        return context
```

### Migration Order
1. Define the canonical `SearchResult` model and `RetrievalContext` in `retrieval/models.py`.
2. Move `context_builder.py`, `reranker.py`, and `vector_store.py` into the `retrieval/` directory (or create a facade in `retrieval/pipeline.py` that wraps them without moving them immediately if it causes too much breakage, but moving is cleaner). Actually, the prompt says "The exact module structure is flexible, but aim for something conceptually like: retrieval/..."
3. Implement `RetrievalPipeline` in `retrieval/pipeline.py`.
4. Migrate `agents/crew_orchestrator.py` (v2 pipeline) to use `RetrievalPipeline.run()`.
5. Migrate `api/query.py` (legacy pipeline) to use `RetrievalPipeline.run()`.
6. Add unit tests for `RetrievalPipeline`.

## 6. Risks & Behavior Preservation
- **Preservation Rule**: We must NOT change top-k values, reranker thresholds, BM25 weights (0.4), or FAISS weights (0.6).
- **Risk**: The current `SearchResult` imports are messy (aliasing `RerankSearchResult`). A unified model in `retrieval/models.py` will fix this but requires careful updates to `ContextBuilder` and `ConfidenceScorer` which depend on specific field names (`section_number`, `law_type`, `text`, `score`).
