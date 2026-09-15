# Phase 6A: Agent Architecture Audit

## 1. Executive Summary

JustiAssist utilizes a native Python orchestration system modeled after CrewAI. The architecture currently spans across multiple modules, primarily `agents/crew_orchestrator.py` and `api/query.py`. Recent updates (Phase 5) introduced canonical `RetrievalPipeline` and `GroundedGenerationPipeline` components. However, the audit reveals significant orchestration duplication and bypassing, particularly between the REST (`/query`) and SSE streaming (`/api/query/stream`) endpoints in `api/query.py` versus the intended orchestrator in `crew_orchestrator.py`. The recommended Phase 6B architecture is to unify all orchestration behind a strict, single `AgentState`-based pipeline orchestrator that leverages the existing native components while maintaining the strict evidence validation gates.

## 2. Current Agent Inventory

| Agent / Component | Location | Responsibility | Status |
|------------------|----------|----------------|--------|
| `JustiAssistCrew` | `agents/crew_orchestrator.py` | Main pipeline orchestrator coordinating other agents, tools, and generation. | **ACTIVE** (Used by `/api/v2/query` and streaming equivalents, but bypassed by `/query`) |
| `QueryClassifier` | `agents/query_classifier.py` | Determines `QueryType` (Legal Info, Bail, Document) via LLM with keyword fallback. | **ACTIVE** |
| `QueryReformulator` | `agents/query_reformulator.py` | Expands legal terms, extracts sections and law types. | **ACTIVE** |
| `BailEvaluator` | `agents/bail_evaluator.py` | Heuristic and LLM-based bail likelihood assessment. | **ACTIVE** |
| `FeedbackEvaluator` | `agents/feedback_evaluator.py` | Validates grounding, citations, and hallucination in responses. | **ACTIVE** (Used in `review_output`) |
| `FeedbackLoop` | `agents/feedback_evaluator.py` | Recursive feedback manager to regenerate until pass. | **UNUSED / DEAD** (Generation moved to `GroundedGenerationPipeline`) |

## 3. Current Orchestration Responsibilities

Treating `agents/crew_orchestrator.py` as the primary orchestration hub, its current responsibilities are:

| Responsibility | Current Location | Should Stay in Orchestrator? | Target Component |
| -------------- | ---------------- | ---------------------------- | ---------------- |
| Query Classification | `JustiAssistCrew.process_query` | No | `RouterAgent` / Pipeline Node |
| Query Reformulation | `JustiAssistCrew.process_query` | No | `ResearchAgent` |
| Retrieval | `JustiAssistCrew.process_query` | No | `ResearchAgent` |
| External Retrieval | `JustiAssistCrew.process_query` | No | `ResearchAgent` |
| Evidence Validation | `JustiAssistCrew.process_query` | No | `VerificationAgent` or pipeline edge |
| Generation | `JustiAssistCrew.process_query` | No | `ResponseAgent` |
| Confidence Scoring | `JustiAssistCrew.process_query` | No | `ResearchAgent` / `AnalysisAgent` |
| Review / Metrics | `JustiAssistCrew.process_query` | No | `VerificationAgent` |
| SSE Emission | Callbacks in orchestrator | Yes (via event bus) | Orchestrator event emitter |

## 4. QueryType and Routing Analysis

- **Query Types**: `LEGAL_INFO`, `BAIL_QUERY`, `DOCUMENT_QUERY`, `UNKNOWN`
- **Detection**: Determined by `QueryClassifier` primarily using LLM semantics, with a fast heuristic/keyword fallback.
- **Routing Effects**:
  - `DOCUMENT_QUERY`: Bypasses strict confidence scoring, relies strictly on uploaded document context.
  - `BAIL_QUERY`: Triggers external Indian Kanoon retrieval and specific `BailEvaluator` logic.
- **Ambiguities/Risks**: Routing decisions are executed independently in `api/query.py` and `crew_orchestrator.py`, leading to potential divergence in how external search triggers are handled.

## 5. Execution-path Analysis

### A. Normal statutory question
`API` → `QueryClassifier` (LEGAL_INFO) → `QueryReformulator` → `RetrievalPipeline` (Statutory/CaseLaw) → Confidence Score → Validation → `GroundedGenerationPipeline` → Response

### B. Case-law question
`API` → `QueryClassifier` (LEGAL_INFO/BAIL_QUERY) → `QueryReformulator` → `RetrievalPipeline` → Trigger External (Kanoon) → Validation → Generation → Response

### C. Bail question
`API` → `QueryClassifier` (BAIL_QUERY) → `QueryReformulator` (adds CrPC context) → Retrieval → Trigger External Kanoon → Validation → Generation + `BailEvaluator` → Response

### D. Uploaded-document-only question
`API` → `QueryClassifier` (DOCUMENT_QUERY) → Bypass standard confidence scoring → Retrieve from Session Documents → Generation → Response

### E. Query requiring external evidence (New law / low confidence)
`API` → Classifier → Reformulator → Local Retrieval → LOW CONFIDENCE detected → Trigger `ExternalRetriever` (Firecrawl) → Inject to `EvidenceSet` → `EvidenceValidator` → Generation → Response

## 6. Bypass Analysis

Several critical bypasses exist in the current implementation:
- **Orchestration Bypass**: `/query` and `/api/query/stream` in `api/query.py` manually orchestrate the entire pipeline (classification, retrieval, generation) instead of calling `crew_orchestrator.py`.
- **Validation Bypass (Critical)**: In `api/query.py` (`query_stream`), `ExternalRetriever` is called *after* generation is complete. The external results are returned to the user but are not validated or used as grounded context for generation.
- **Evidence Integrity Risk**: `crew_orchestrator.py` modifies the `EvidenceSet` object directly by appending `external_results` before running it through `EvidenceValidator`.
- **Confidence Scoring Bypass**: `DOCUMENT_QUERY` manually forces high confidence.

## 7. Duplication Analysis

| Logic | Location 1 | Location 2+ | Canonical Owner |
| ----- | ---------- | ----------- | --------------- |
| Pipeline Orchestration | `agents/crew_orchestrator.py` | `api/query.py` (`process_query`, `query_stream`) | `PipelineOrchestrator` |
| External Retrieval Triggers | `agents/crew_orchestrator.py` | `api/query.py` | `ResearchAgent` |
| Citation Construction | `agents/crew_orchestrator.py` | `api/query.py` | `ResponseAgent` |
| Kanoon & News Logic | `agents/crew_orchestrator.py` (via `ExternalRetriever`) | `api/query.py` (Manual concurrent fetches) | `ResearchAgent` |

## 8. Legacy/Dead Code Analysis

- **`agents/feedback_evaluator.py:FeedbackLoop`**: DEAD / UNUSED. The recursive grounding logic has been superseded by `GroundedGenerationPipeline`.
- **`api/query.py:process_query`**: LEGACY / DUPLICATED. Fully duplicates the orchestration found in `JustiAssistCrew`.
- **`api/query.py:query_stream`**: LEGACY / DUPLICATED. Fully duplicates the streaming orchestration logic.

## 9. Agent Contract Assessment

Current agents (`QueryClassifier`, `QueryReformulator`, `BailEvaluator`) do not share a unified state contract. They return varied, bespoke `dataclass` objects and rely on the orchestrator to unpack and mutate a global `CrewResult`.
To fit a target `AgentState` pattern:
- Agents must accept an immutable or controlled `AgentState` object.
- Agents must return structured diffs or state updates rather than arbitrary dictionaries or specific dataclasses.
- SSE emission must be abstracted from the agents.

## 10. Recommended Phase 6B Target Architecture

**Architecture**: Convert to a unified Native Pipeline using an explicit `AgentState` object, migrating away from the `JustiAssistCrew` god object and redundant endpoint logic. 

**Flow**:
```text
RouterAgent (Classification)
    ↓
ResearchAgent (Local + External Retrieval governed by evidence validation)
    ↓
AnalysisAgent (Confidence Scoring / Bail Evaluation)
    ↓
VerificationAgent (Evidence Validation)
    ↓
ResponseAgent (Grounded Generation & Citation Formatting)
```
- The existing components (`QueryClassifier`, `RetrievalPipeline`, `GroundedGenerationPipeline`) are robust and should be wrapped by these lightweight Agents.
- The `api/query.py` endpoints should only invoke this unified pipeline, completely removing inline orchestration.

## 11. Explicit Out-of-Scope Items
- No changes to faiss/BM25 retrieval logic.
- No changes to generation prompts or `GroundedGenerationPipeline`.
- No new LLM models or framework additions (no CrewAI, LangGraph, etc).
- No new vector databases.

## 12. Risks and Migration Considerations
- **Risk**: Moving streaming out of the API layer into a unified orchestrator may complicate SSE event propagation.
- **Migration**: Ensure the `AgentState` contains all necessary context (e.g., session IDs, chat history) without bloating the object. The `ExternalRetriever` logic must be unified to guarantee it runs *before* validation and generation.
