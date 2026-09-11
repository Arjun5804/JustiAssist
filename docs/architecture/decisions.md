# JustiAssist — Architecture Decision Records

> **Phase 0A** | Generated 2026-09-11

---

## ADR-001: Native Agent Framework Over CrewAI

**Status**: Accepted (already implemented)

**Context**: CrewAI was the original target framework for agent orchestration. However, CrewAI requires Python < 3.14, and the project runs on Python 3.14.2.

**Decision**: The team implemented a lightweight native agent framework in `crew_orchestrator.py` that mimics the CrewAI Agent/Task/Crew pattern without the dependency.

**Consequences**:
- ✅ No Python version constraint
- ✅ Full control over LLM routing and tool integration
- ✅ Zero dependency issues
- ❌ `crewai>=0.108.0` remains in `requirements.txt` (should be removed)
- ❌ `agents/tools/` directory contains 3 dead files importing `crewai.tools.BaseTool`
- ❌ The native framework lacks the sophisticated task delegation, memory, and planning that CrewAI provides

**Action Items**: Remove `crewai` and `crewai-tools` from `requirements.txt`. Remove or archive `agents/tools/`.

---

## ADR-002: Dual FAISS Index (Statutory + Case Law)

**Status**: Accepted (already implemented)

**Context**: Legal documents have fundamentally different characteristics — statutory provisions are short and precise, while case law judgments are long and narrative.

**Decision**: Maintain separate FAISS indices with different chunking parameters:
- Statutory: 380-token chunks, 65 overlap, BM25 + semantic hybrid search
- Case Law: 550-token chunks, 100 overlap, semantic search only

**Consequences**:
- ✅ Domain-appropriate chunking improves retrieval quality
- ✅ Queries can target the appropriate index
- ❌ Case law index lacks BM25 component (limits keyword matching for specific sections in judgments)
- ❌ No cross-index retrieval (statutory and case law are never searched together in a single query)

---

## ADR-003: Groq as Primary LLM with Ollama Fallback

**Status**: Accepted (already implemented)

**Context**: The system needs reliable LLM inference for classification, generation, and verification.

**Decision**: Use Groq Cloud (llama-3.3-70b-versatile) as primary with Ollama (llama3.2) as local fallback.

**Consequences**:
- ✅ Fast inference via Groq's LPU
- ✅ Offline capability via Ollama fallback
- ❌ No health check for Groq availability
- ❌ Quality gap between 70B primary and 8B fallback is significant
- ❌ No retry/circuit-breaker pattern for Groq API failures

---

## ADR-004: In-Memory Document Sessions

**Status**: Accepted (with known limitations)

**Context**: Users can upload legal documents (FIRs, chargesheets, bail applications) for analysis.

**Decision**: Uploaded documents are chunked and indexed in per-session FAISS indices held in process memory.

**Consequences**:
- ✅ Fast, no additional infrastructure
- ❌ **Data loss on server restart** — all uploaded documents and their indices are lost
- ❌ No multi-process support
- ❌ Memory pressure with many concurrent sessions

**Future**: Consider persistent session storage (file-based or database-backed FAISS indices).

---

## ADR-005: SQLite for User Data and Chat History

**Status**: Accepted (already implemented)

**Context**: The system needs user accounts and conversation persistence.

**Decision**: Use SQLite via SQLAlchemy for users and chat messages.

**Consequences**:
- ✅ Zero-infrastructure persistence
- ✅ Good enough for single-server deployment
- ❌ `init_db()` runs on module import, making test isolation difficult
- ❌ Not suitable for multi-server deployment
- ❌ No migration framework (Alembic)

---

## ADR-006: Dataset Priority System

**Status**: Accepted (already implemented)

**Context**: Datasets exist in two locations (`project datasets/` for full versions, `data/` for small/specialized versions) with potential duplicates.

**Decision**: `config.discover_datasets()` implements a priority system:
1. Scan `project datasets/` first (priority)
2. Scan `data/` second, skipping known redundant files (listed in `REDUNDANT_FILES` set)

**Consequences**:
- ✅ Full datasets used when available
- ✅ Small specialized datasets (special acts, glossary) supplemented
- ❌ Redundancy detection is name-based, not content-based
- ❌ No versioning or checksum validation for datasets

---

## ADR-007: Pre-Response Citation Validation

**Status**: Accepted (already implemented)

**Context**: LLMs can hallucinate legal section numbers, which is unacceptable in a legal assistant.

**Decision**: Run `CitationValidator` before returning any response. Extract all section citations from the generated text and verify they exist in the retrieved context. Calculate a fabrication score and penalize confidence.

**Consequences**:
- ✅ Catches fabricated citations before they reach the user
- ✅ Fabrication score provides quantitative trust signal
- ❌ Regex-based extraction can miss complex citation patterns
- ❌ Fuzzy matching (`_citation_in_context`) can produce false positives (any numeric match)
- ❌ `sanitize_response()` was neutered (returns response unchanged) — warnings only in structured data

---

## ADR-008: No New Frameworks in Phase 0

**Status**: Active

**Context**: The codebase needs significant restructuring before introducing new frameworks.

**Decision**: Phase 0 establishes the architecture baseline. No new frameworks (CrewAI, Agno, LangGraph, vector databases, PostgreSQL, Redis, Docker) will be introduced until the existing codebase is properly modularized and tested.

**Consequences**:
- ✅ Reduces risk of building on unstable foundations
- ✅ Forces understanding of current architecture before changes
- ❌ Delays potential improvements from better frameworks
