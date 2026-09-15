# Phase 5: Controlled External Evidence & Source Governance

## Overview
Phase 5 addresses the integration of external data sources (Firecrawl, Indian Kanoon, and legal news) into the JustiAssist grounded generation pipeline. Prior to this phase, external context was loosely appended or used strictly for UI enrichment. Phase 5 creates a robust, deterministic boundary ensuring that external information behaves exactly like semantic local hits, with strict provenance and authority controls.

## Architecture
```text
                 ┌───────────┴───────────┐
                 ▼                       ▼
          Local Retrieval          External Retrieval
                 │                       │
                 │                ┌──────┴──────┐
                 │                │ Firecrawl   │
                 │                │ Kanoon      │
                 │                │ News        │
                 │                └──────┬──────┘
                 │                       │
                 │                Source Governance
                 │                       │
                 │                Temporal Metadata
                 │                       │
                 └──────────┬────────────┘
                            ▼
                       EvidenceSet
                            │
                            ▼
                    EvidenceValidator
                            │
                            ▼
                 ValidatedEvidenceSet
```

## Implementation Details

### 1. `ExternalRetriever`
Located in `retrieval/external.py`, this class centralizes all non-local fetching. It runs tasks concurrently and applies normalization to raw results. It only fires on explicit conditions (e.g., Domain Mismatch, New Law trigger, Bail Query).

### 2. `AuthorityClassifier`
This component uses exact domain matching to deterministically assign an `AuthorityLevel`.
- `.india.gov.in` -> `PRIMARY_OFFICIAL`
- `indiankanoon.org` -> `TRUSTED_LEGAL`
- News domains -> `NEWS`
- Anything else -> `UNKNOWN`

### 3. Normalization and Canonical IDs
Every external result is mapped to the `SearchResult` abstraction.
- A stable `chunk_id` is generated deterministically (`ext_{type}_{hash}`).
- Temporal metadata (`published_at`, `retrieved_at`) is preserved if present.
- We **never** fabricate effective dates.
- Fallback news is explicitly flagged with `is_fallback=True` and filtered out of the legal evidence set completely.

### 4. Phase 4 Integration
The outputs from local and external retrieval are combined into a single raw `EvidenceSet`. 
This `EvidenceSet` then passes through `EvidenceValidator`, producing a `ValidatedEvidenceSet`. The `GroundedGenerationPipeline` treats them as standard evidence. `ClaimVerifier` receives the entire evidence text and can detect `CONFLICTING` material. If the system cannot resolve the conflict natively, it abstains.

## Out of Scope
- Temporal legal reasoning (supersession graphs)
- New agent frameworks or Kubernetes integration
- Modifications to FAISS, BM25, or local embedding logic
