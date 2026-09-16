# JustiAssist — Current Architecture Baseline

> **Phase 0A** | Generated 2026-09-11 | Commit: `docs: establish JustiAssist architecture baseline`

---

## 1. System Overview

JustiAssist is an **Intelligent RAG & Agentic Bail Support System for Indian Legal Domain**. It combines a FastAPI backend with a React (Vite) frontend, FAISS vector search, a lightweight agent orchestrator (CrewAI-style but native Python), and multiple external API integrations.

```mermaid
graph TB
    subgraph Frontend["React Frontend (Vite, port 3000)"]
        UI[Chat UI / Query Input]
        RC[Response Card]
        PV[Pipeline Visualizer]
        CP[CasePredictAI]
        CA[Counter Arguments]
        DG[Document Generate]
        LS[Legal Sandbox]
        DU[Document Upload]
        KS[Kanoon Search]
        NW[News Widget]
        Auth[Auth Page]
    end

    subgraph Backend["FastAPI Backend (port 8000)"]
        APP[app.py — 2547 lines, monolith]
        
        subgraph Agents
            QC[QueryClassifier]
            QR[QueryReformulator]
            BE[BailEvaluator]
            FE[FeedbackEvaluator]
            CO[CrewOrchestrator]
        end

        subgraph RAGPipeline["Enhanced RAG Pipeline"]
            VS[VectorStore — FAISS + BM25]
            RR[LegalReranker]
            CB[ContextBuilder]
            CS[ConfidenceScorer]
            CV[CitationValidator]
        end

        subgraph Services
            LLM[LLMProvider — Groq + Ollama]
            IK[IndianKanoonAPI]
            NS[LegalNewsScraper]
            FC[Firecrawl Web Search]
            DB[SQLAlchemy + SQLite]
            AU[Auth — JWT + bcrypt]
            CM[ChatMemory]
            PE[PipelineEvents — SSE]
            AL[AuditLogger — JSONL]
            MT[MetricsCollector]
        end

        subgraph Data["Vector Indices"]
            SI[statutory/index.faiss — 113 MB]
            CI[case_law/index.faiss — 186 MB]
        end
    end

    UI --> |SSE /api/v2/query/stream| APP
    UI --> |POST /api/v2/query| APP
    UI --> |POST /query (legacy)| APP
    APP --> CO
    CO --> QC --> QR --> VS --> RR --> CB --> CS
    CO --> LLM
    CO --> FC
    CO --> CV --> FE
    CO --> BE
    APP --> IK
    APP --> NS
    APP --> DB
```

---

## 2. Request Lifecycle (Full Trace)

A query through `POST /api/v2/query` or `GET /api/v2/query/stream` follows this pipeline:

### Stage-by-Stage Flow

```
Frontend (React)
  │
  ├─ POST /api/v2/query  ──OR──  GET /api/v2/query/stream (SSE)
  │
  ▼
app.py  process_query_v2() / query_stream_v2()
  │
  ├─ 1. Auth: get_current_user_optional()  →  JWT decode → SQLite User lookup
  ├─ 2. Chat Context: format_history_for_context()  →  last 6 messages, 2000 chars
  ├─ 3. Session Documents: session_manager.get_session()  →  FAISS search over uploaded docs
  │
  ▼
crew_orchestrator.process_query()
  │
  ├─ STAGE 1 — ClassifierAgent
  │    QueryClassifier.classify(query)
  │    LLM call (Groq) → parse JSON → QueryType (LEGAL_INFO | BAIL_QUERY | DOCUMENT_QUERY)
  │    Fallback: keyword heuristics with weighted scores
  │
  ├─ STAGE 2 — Query Reformulation
  │    QueryReformulator.reformulate(query)
  │    Expand acronyms (50+ legal terms), extract sections (regex), synonym expansion
  │    Output: enhanced_query, extracted_sections, extracted_law_types
  │
  ├─ STAGE 3 — ResearcherAgent (Retrieval)
  │    VectorStore.hybrid_search_statutory(enhanced_query, top_k=45)
  │      ├─ FAISS semantic search (normalized cosine, bge-m3 embeddings)
  │      ├─ BM25Okapi keyword search (legal-aware tokenizer)
  │      └─ Reciprocal Rank Fusion (semantic_weight=0.6, bm25_weight=0.4)
  │    LegalReranker.rerank(results, sections, mode=precision|balanced)
  │      ├─ Statute Presence score (40%)
  │      ├─ Section Match score (30%)
  │      ├─ Legal Entity Density (15%)
  │      └─ Semantic Score (15%)
  │    → top 15 statutory results
  │    [If BAIL_QUERY]: VectorStore.search_case_law() → rerank(mode=recall) → top 10
  │
  ├─ STAGE 4 — Confidence Scoring
  │    ConfidenceScorer.compute_confidence()
  │      ├─ Section Coverage (requested vs. retrieved)
  │      ├─ Intent Matching (concept keyword overlap)
  │      ├─ Source Redundancy (multi-chunk confirmation)
  │      ├─ Legal Completeness (required provisions check)
  │      └─ Average Relevance (mean similarity)
  │    → overall_score → ConfidenceLevel (HIGH|MEDIUM|LOW|VERY_LOW)
  │    → grounding_status: pass | partial | fail
  │
  ├─ STAGE 5 — WebIntelAgent (Conditional)
  │    Triggered when: low confidence OR new law (BNS/BNSS/BSA) OR special rule OR domain mismatch
  │    Firecrawl.search(query) → up to 3 web results, markdown format
  │
  ├─ STAGE 6 — Generation
  │    ContextBuilder.build_structured_context() → grouped by evidence type & law type
  │    [If BAIL_QUERY]:
  │      BailEvaluator.evaluate() → rule-based heuristics + LLM reasoning
  │      Output: BailEvaluation with likelihood, reasoning, precedents
  │    [If LEGAL_INFO]:
  │      Inline prompt construction → call_llm() via Groq (or Ollama fallback)
  │    [If DOCUMENT_QUERY]:
  │      Document-aware prompt → call_llm()
  │
  ├─ STAGE 7 — QualityReviewerAgent
  │    [If web_context exists]:
  │      LLM verification prompt → cross-validate local vs web sources
  │    CitationValidator.validate(response, context_chunks)
  │      → extract citations from response, match against context sections
  │      → fabrication_score, invalid_sections
  │    [If invalid]: sanitize_response(), penalize confidence
  │    FeedbackEvaluator.evaluate(response, context, query)
  │      → grounding_score, unsupported_claims, citation_count
  │    Adjust confidence based on grounding score
  │
  ├─ STAGE 8 — Enrichment (Parallel, non-blocking)
  │    asyncio.gather(fetch_kanoon(), fetch_news())
  │    IndianKanoonAPI.search() → top 3 judgment citations
  │    LegalNewsScraper.get_news() → top 2 news articles
  │
  └─ RESPONSE
       CrewResult → to_response_dict()
       Save to chat_messages (SQLite) if authenticated
       → JSON response with: answer, citations, confidence, bail_assessment,
         grounding_status, kanoon_cases, news_context, processing_info
```

---

## 3. Dataset Inventory

### 3.1 `data/` — Secondary / Specialized Datasets (Small)

| File | Format | Records | Size | Schema | Domain | Type | Source |
|---|---|---|---|---|---|---|---|
| `ipc_sections_dataset.csv` | CSV | 106 | 16 KB | Section, Description, Offense, Punishment, Cognizable, Bailable | Criminal | Statutory | Hand-curated |
| `crpc_sections_dataset.csv` | CSV | 45 | 12 KB | Section, Chapter, Chapter_name, Section_name, Description | Criminal Procedure | Statutory | Hand-curated |
| `bail_provisions.csv` | CSV | 64 | 4 KB | section, law_type, bailable, max_punishment_years, cognizable, compoundable, description, crpc_section, bnss_equivalent | Bail Classification | Statutory | Hand-curated |
| `bail_judgments.csv` | CSV | 15 | 5 KB | case_title, court, date, judgment_text, sections_cited, case_id | Bail Case Law | Case Law | Hand-curated |
| `crpc_bail_provisions.csv` | CSV | 8 | 5 KB | section, law_type, chapter, description | Bail Procedure | Statutory | Hand-curated |
| `constitution_articles.csv` | CSV | 27 | 3 KB | article, part, description | Constitutional | Statutory | Hand-curated |
| `bns_provisions.csv` | CSV | 24 | 1.4 KB | section, bns_equivalent, law_type, bailable, etc. | BNS (New Criminal) | Statutory | Hand-curated |
| `bnss_provisions.csv` | CSV | 29 | 2.1 KB | section, law_type, description, crpc_equivalent | BNSS (New Procedure) | Statutory | Hand-curated |
| `bsa_provisions.csv` | CSV | 30 | 2 KB | section, law_type, description, evidence_act_equivalent | BSA (New Evidence) | Statutory | Hand-curated |
| `ndps_sections.csv` | CSV | 17 | 2.5 KB | section, law_type, description, bailable, max_punishment_years, cognizable | NDPS Act | Statutory | Hand-curated |
| `pmla_sections.csv` | CSV | 11 | 1.3 KB | (same schema as NDPS) | PMLA | Statutory | Hand-curated |
| `pocso_sections.csv` | CSV | 16 | 1.7 KB | (same schema as NDPS) | POCSO Act | Statutory | Hand-curated |
| `scst_sections.csv` | CSV | 10 | 1.4 KB | (same schema as NDPS) | SC/ST Act | Statutory | Hand-curated |
| `uapa_sections.csv` | CSV | 12 | 1.2 KB | (same schema as NDPS) | UAPA | Statutory | Hand-curated |
| `arbitration_act.csv` | CSV | 6 | 2.3 KB | act_name, section, description, notes | Arbitration | Statutory | Hand-curated |
| `civil_law.csv` | CSV | 16 | 2.3 KB | act_name, section, description, notes | Civil | Statutory | Hand-curated |
| `commercial_law.csv` | CSV | 19 | 2.5 KB | act_name, section, description, notes | Commercial | Statutory | Hand-curated |
| `cpc_sections_dataset.csv` | CSV | 19 | 2.4 KB | Section, Order, Description | Civil Procedure | Statutory | Hand-curated |
| `labour_and_property.csv` | CSV | 16 | 1.8 KB | act_name, section, description, notes | Labour/Property | Statutory | Hand-curated |
| `limitation_act.csv` | CSV | 11 | 2 KB | act_name, section, description, limitation_period, starting_point | Limitation | Statutory | Hand-curated |
| `special_acts.csv` | CSV | 16 | 2.2 KB | act_name, section, description, bailable, punishment, cognizable | Special Laws | Statutory | Hand-curated |
| `specific_relief_act.csv` | CSV | 8 | 2.7 KB | act_name, section, description, notes | Specific Relief | Statutory | Hand-curated |
| `legal_history.csv` | CSV | 24 | 4.8 KB | Era, Year, Event, Description, Significance | Legal History | Secondary | Hand-curated |
| `bail_qa.json` | JSON | 10 | 3.2 KB | question, answer | Bail | QA | Hand-curated |
| `constitution_qa.json` | JSON | 10 | 2.6 KB | question, answer | Constitutional | QA | Hand-curated |
| `crpc_qa.json` | JSON | 10 | 3.4 KB | question, answer | Criminal Procedure | QA | Hand-curated |
| `ipc_qa.json` | JSON | 10 | 3.3 KB | question, answer | Criminal | QA | Hand-curated |
| `legal_glossary.json` | JSON | 27 | 5.4 KB | term, definition | General | Secondary | Hand-curated |
| `legal_news.json` | JSON | — | 16 KB | (Dynamic) | News | Dynamic/Cache | GNews API |
| `kanoon_cache/` | JSON | 46 files | ~500 KB | (API response cache) | Case Law | Cache | Indian Kanoon API |

### 3.2 `project datasets/` — Full / Production Datasets

| File | Format | Records | Size | Schema | Domain | Type | Source |
|---|---|---|---|---|---|---|---|
| `bns_dataset.csv` | CSV | 400 | 130 KB | Section, Subsection, Cause, Explanation, Illustration, Effect | BNS (New Criminal) | Statutory | External dataset |
| `bns_sections.csv` | CSV | 358 | 389 KB | Chapter, Chapter_name, Chapter_subtype, Section, Section_name, Description | BNS (New Criminal) | Statutory | External dataset |
| `crpc_sections.csv` | CSV | 534 | 694 KB | Chapter, Chapter_name, Chapter_subtype, Section, Section_name, Description | Criminal Procedure | Statutory | External dataset |
| `ipc_sections.csv` | CSV | 444 | 400 KB | Description, Offense, Punishment, Section | IPC (Criminal) | Statutory | External dataset |
| `indian_bail_judgments.csv` | CSV | 1,200 | 1.7 MB | case_id, case_title, court, date, judge, ipc_sections, bail_type, bail_outcome, facts, legal_issues, judgment_reason, summary, + 12 more | Bail Case Law | Case Law | External dataset |
| `supreme_court_judgments.csv` | CSV | 47,400 | 8.2 MB | diary_no, Judgement_type, case_no, pet, res, pet_adv, res_adv, bench, judgement_by, judgment_dates, temp_link, language | Supreme Court | Case Law | External dataset |
| `constitution_qa.json` | JSON | 4,082 | 1.2 MB | question, answer | Constitutional | QA | External dataset |
| `crpc_qa.json` | JSON | 8,194 | 2.1 MB | question, answer | Criminal Procedure | QA | External dataset |
| `ipc_qa.json` | JSON | 2,267 | 660 KB | question, answer | Criminal | QA | External dataset |
| `indian_laws.json` | JSON | 1,931 | 1.6 MB | title, description | Multi-domain | Statutory | External dataset |
| `IndicLegalQA Dataset_10K_Revised.json` | JSON | 10,000 | 4.9 MB | case_name, judgement_date, question, answer | Multi-domain | QA | IndicLegalQA benchmark |
| `IndicLegalQA Dataset_10K.json` | JSON | 10,002 | 4.9 MB | case_name, judgment_date, question, answer | Multi-domain | QA | IndicLegalQA (superseded) |

### 3.3 Dataset → Index Mapping

```
config.py: discover_datasets()  →  data_loader.py: DataLoader  →  chunker.py: TextChunker

STATUTORY INDEX (vector_stores/statutory/):
  ├─ Priority CSV: bns_dataset, bns_sections, crpc_sections, ipc_sections
  ├─ Priority JSON: constitution_qa, crpc_qa, ipc_qa, indian_laws, IndicLegalQA_Revised
  ├─ Secondary CSV: bail_provisions, constitution_articles, crpc_bail_provisions,
  │   bns_provisions, bnss_provisions, bsa_provisions, ndps, pmla, pocso, scst, uapa,
  │   arbitration, civil_law, commercial_law, cpc, labour, limitation, special_acts,
  │   specific_relief, legal_history
  └─ Secondary JSON: legal_glossary

CASE LAW INDEX (vector_stores/case_law/):
  ├─ Priority CSV: indian_bail_judgments, supreme_court_judgments
  └─ Secondary CSV: bail_judgments (data/)

SKIPPED (redundant copies in data/):
  ipc_sections_dataset.csv, crpc_sections_dataset.csv, bns_provisions.csv,
  bnss_provisions.csv, bsa_provisions.csv, bail_judgments.csv, bail_provisions.csv,
  constitution_qa.json, ipc_qa.json, crpc_qa.json, bail_qa.json,
  legal_news.json, IndicLegalQA Dataset_10K.json
```

### 3.4 Index Build Scripts

The index builder lives inside `app.py` at endpoint `POST /build-indices` (line 1107). It calls:

1. `data_loader.DataLoader()` — auto-discovers datasets via `config.discover_datasets()`
2. `DataLoader.load_all_statutory()` → parses CSV/JSON → `LegalDocument` list
3. `DataLoader.load_case_law()` → same for case law
4. `chunker.TextChunker.chunk_documents()` → domain-aware chunking → `TextChunk` list
5. `VectorStore.build_statutory_index(chunks)` → FAISS + BM25
6. `VectorStore.build_case_law_index(chunks)` → FAISS
7. `VectorStore.save()` → persists to `vector_stores/statutory/` and `vector_stores/case_law/`

There is also `colab_build.ipynb` for building indices in Google Colab.

---

## 4. Agent Inventory

| Agent | Location | Classification | LLM Required | Description |
|---|---|---|---|---|
| **QueryClassifier** | `agents/query_classifier.py` | Router/Classification | Yes (Groq) | Classifies queries into LEGAL_INFO, BAIL_QUERY, DOCUMENT_QUERY via LLM then keyword fallback |
| **QueryReformulator** | `agents/query_reformulator.py` | Utility | No | Rule-based query expansion: acronyms, synonyms, section extraction. No LLM. |
| **BailEvaluator** | `agents/bail_evaluator.py` | Analysis | Yes (Groq) | Specialized bail assessment with rule-based heuristics (bailable/non-bailable tables) + LLM reasoning |
| **FeedbackEvaluator** | `agents/feedback_evaluator.py` | Verification | No | Grounding validation: checks citations against context, unsupported claims detection. Rule-based. |
| **JustiAssistCrew** (Orchestrator) | `agents/crew_orchestrator.py` | Router/Classification | Yes | Lightweight agentic pipeline coordinator. Runs stages 1-8 sequentially. |
| **CitationValidator** | `citation_validator.py` | Verification | No | Pre-response citation validation via regex matching against context sections |
| **ConfidenceScorer** | `confidence_scorer.py` | Verification | No | Multi-factor retrieval confidence (section coverage, intent matching, source redundancy) |
| **LegalReranker** | `reranker.py` | Retrieval/Research | No | Two-stage reranking with legal-specific signals (statute presence, section match, entity density) |
| **ContextBuilder** | `context_builder.py` | Utility | No | Structures retrieved chunks by evidence type and law type for LLM prompts |

### Agent Tools (CrewAI-compatible, currently unused)

| Tool | Location | Status |
|---|---|---|
| `VectorSearchTool` | `agents/tools/vector_search_tool.py` | **Dead code** — imports `crewai.tools.BaseTool` which isn't installed (Python 3.14) |
| `FirecrawlSearchTool` | `agents/tools/firecrawl_tool.py` | **Dead code** — same issue |
| `KanoonSearchTool` | `agents/tools/kanoon_tool.py` | **Dead code** — same issue |

> **Note**: The `agents/tools/` directory contains CrewAI tool wrappers that cannot be imported because CrewAI requires Python < 3.14 and the project runs on 3.14.2. The orchestrator reimplements the tool logic inline.

### Duplicate / Overlapping Implementations

1. **Legacy `/query` endpoint** (line 584) duplicates the entire v2 pipeline from `crew_orchestrator.process_query()` — same retrieval, reranking, confidence scoring, generation, citation validation, and enrichment logic is repeated inline across ~500 lines.
2. **Legacy `/api/query/stream`** (line 1908) duplicates the v2 SSE streaming logic.
3. **`services/hybrid_retriever.py`** defines `HybridContext`, `KanoonCase`, `NewsItem` dataclasses that overlap with equivalents in `crew_orchestrator.py` — the hybrid retriever appears partially integrated but largely bypassed.

---

## 5. Retrieval Architecture

### Vector Store

- **Engine**: FAISS `IndexFlatIP` (inner product on normalized vectors = cosine similarity)
- **Embedding Model**: `BAAI/bge-m3` (1024-dim), configurable via env
- **Dual Index**:
  - `statutory/` — 113 MB FAISS index + 22 MB metadata + 14 MB BM25 corpus
  - `case_law/` — 186 MB FAISS index + 12 MB metadata (no BM25)
- **Hybrid Search**: Reciprocal Rank Fusion of FAISS semantic + BM25 keyword scores
- **Reranking**: 4-signal weighted reranking (statute presence, section match, entity density, semantic)

### Chunking

- Domain-aware chunk sizes: Statutory (380 tokens, 65 overlap), Case Law (550, 100), QA (280, 35)
- Token counting via `tiktoken`

### External Sources

| Source | Integration | Auth | Caching |
|---|---|---|---|
| **Firecrawl** | Web search + scrape | API key | None |
| **Indian Kanoon** | Case law citations | API key | File-based (JSON, `data/kanoon_cache/`) |
| **Google News (GNews)** | Legal news | None | File-based (`data/legal_news.json`) |

---

## 6. External / Web Sources

| Source | Used In | Purpose | Failure Mode |
|---|---|---|---|
| **Groq Cloud API** | LLMProvider (primary) | LLM inference (llama-3.3-70b-versatile) | Falls back to Ollama |
| **Ollama** | LLMProvider (fallback) | Local LLM (llama3.2) | Returns error |
| **Firecrawl** | CrewOrchestrator Stage 5 | Web verification for gaps, new laws, special rules | Skipped silently |
| **Indian Kanoon API** | Stage 8 Enrichment | Live case citations | Skipped with 3s timeout |
| **GNews** | Stage 8 Enrichment | Legal news articles | Skipped silently |

---

## 7. Persistence

| Store | Tech | Location | Purpose |
|---|---|---|---|
| **User DB** | SQLite via SQLAlchemy | `justiassist.db` | Users, Chat Messages |
| **Vector Indices** | FAISS + pickle | `vector_stores/statutory/`, `vector_stores/case_law/` | Retrieval |
| **Audit Logs** | JSONL files | `logs/audit_YYYYMMDD.jsonl` | Retrieval and generation events |
| **API Cache** | JSON files | `data/kanoon_cache/` | Indian Kanoon responses |
| **News Cache** | JSON file | `data/legal_news.json` | GNews articles |
| **Session Documents** | In-memory FAISS | (per-request) | Uploaded document chunks |

> **No persistent session storage**: uploaded document sessions exist only in-memory and are lost on restart.

---

## 8. Frontend Architecture

- **Framework**: React + Vite (JSX, no TypeScript)
- **Routing**: Single-page, tab-based navigation via `NavMenu.jsx`
- **State**: `AuthContext.jsx` for auth; component-local state elsewhere
- **API Communication**: SSE (`EventSource`) for real-time pipeline updates; `fetch` for REST
- **Components** (21 components):
  - Core: QueryInput, ResponseCard, PipelineVisualizer, Header, Footer, NavMenu
  - Features: CasePredictAI, CounterArgument, DocumentGenerate, DocumentUpload, DocumentReview, DocumentCompare, DocumentHub, LegalSandbox, KanoonSearch, NewsWidget
  - UI: Loader, MotionToggle, SampleQueries, StarfieldBg, ChatHistory
- **Auth**: JWT token stored in `localStorage`, attached to requests via `authFetch()`
- **Legacy UI**: `static/index.html` + `static/style.css` (old single-page HTML interface)

---

## 9. Testing

### Test Inventory

| File | Type | What It Tests | Pytest Compatible |
|---|---|---|---|
| `tests/test_section_boost.py` | Integration | IPC section retrieval with boost fix | ✅ (function `test_section_retrieval`) |
| `tests/deep_test.py` | Integration | FAISS index file existence + exact text search | ✅ (async function `test`) |
| `tests/test_kanoon.py` | Integration | Indian Kanoon API connectivity | ✅ (async function `test_kanoon`) |
| `tests/test_search.py` | Integration | Hybrid search + reformulator + reranker | ✅ (async function `test`) |
| `tests/test_rag_retrieve.py` | Integration | RAG retrieval for bail query | ❌ (script, no test function) |
| `tests/test_all_features.py` | Integration | Full crew orchestration + Firecrawl + news | ❌ (script with `if __name__`) |
| `tests/verify_fix.py` | Integration | Confidence scorer section override | ❌ (script) |
| `tests/verify_news_fix.py` | Integration | News scraper source field fix | ❌ (script) |
| `evaluation/eval_harness.py` | Evaluation | Offline retrieval accuracy + confidence alignment | ❌ (standalone script) |

### Test Infrastructure Issues

1. **No pytest fixtures or conftest.py** — each test re-initializes VectorStore (loads 300 MB of indices)
2. **No unit tests** — all tests are integration tests requiring full vector store + embeddings
3. **4 tests discoverable by pytest**, but execution takes 30+ seconds per test due to model loading
4. **Hardcoded paths** — `deep_test.py` has hardcoded `d:\project folder\justiassist\` path
5. **No CI/CD configuration**
6. **No mocking** — all tests hit real vector stores, some hit external APIs

### Test Execution Results

Tests were collected by pytest (4 discovered). Execution requires loading the embedding model and 300 MB of FAISS indices, making the tests very slow (~30s+ per test). The tests are functional integration tests, not unit tests.

---

## 10. Problems (P0 / P1 / P2)

### P0 — Critical (Must Fix)

| ID | Problem | Impact |
|---|---|---|
| **P0-1** | **`app.py` is a 2,547-line monolith** containing 29 endpoints, all business logic inline, two complete duplicate pipelines (legacy + v2). Impossible to test, maintain, or extend. | Blocks all feature work |
| **P0-2** | **No unit tests** — zero isolated tests for any component. All 9 test files are integration scripts requiring full vector store loading. | Cannot safely refactor |
| **P0-3** | **Dead CrewAI dependency** — `requirements.txt` lists `crewai>=0.108.0` but it can't run on Python 3.14. The `agents/tools/` directory (3 files) imports `crewai.tools.BaseTool` and is completely dead code. | Confusing dependency, import errors if tools/ is loaded |
| **P0-4** | **No error boundaries** — pipeline failures in crew orchestrator are caught with bare `except Exception` and return generic error strings. No structured error types, no retry logic. | Silent failures, poor UX |

### P1 — High Priority

| ID | Problem | Impact |
|---|---|---|
| **P1-1** | **Duplicate pipeline logic** — legacy `/query` (lines 584–1096) reimplements the entire v2 pipeline. Any bug fix must be applied twice. | Maintenance burden, divergence risk |
| **P1-2** | **In-memory session documents** — uploaded documents (FAISS index + chunks) live only in process memory. Server restart loses all uploaded documents. | Data loss on restart |
| **P1-3** | **No rate limiting** — endpoints have no rate limiting (except internal Indian Kanoon client). | Abuse risk, API cost exposure |
| **P1-4** | **Hardcoded JWT secret** — `JWT_SECRET_KEY = "justiassist-secret-change-in-production-2026"` as default. | Security vulnerability |
| **P1-5** | **SQLite init on import** — `services/database.py` calls `init_db()` at module import time (line 125), creating tables as a side-effect of importing the module. | Blocks test isolation |
| **P1-7** | **Global mutable state** — 8 global variables in `app.py` (line 78-91) initialized in `lifespan()`. Thread-unsafe. | Race conditions |
| **P1-8** | **No structured logging** — mix of `print()` and `logger` calls throughout. Debug print statements in production code (e.g., line 430: `print(f"FIRECRAWL DEBUG OUTPUT")`). | Noisy logs, no log levels |

### P2 — Improvement

| ID | Problem | Impact |
|---|---|---|
| **P2-1** | **Dataset schema inconsistency** — CSV files use different column names (`Section` vs `section`, `Section _name` with trailing space, `Illustration ` with trailing space). | Fragile parsing |
| **P2-2** | **No embedding model versioning** — `embedding_model.txt` stores model name but indices aren't validated against current model config. Model change = silent retrieval degradation. | Silent quality loss |
| **P2-3** | **Response cache too small** — `LRUCache(max_size=64, ttl_seconds=120)` is tiny and short-lived. | Wasted LLM calls |
| **P2-4** | **No CORS restriction in production** — `ALLOWED_ORIGINS` defaults to localhost variants but env override is a comma-separated string. | Security concern |
| **P2-5** | **Synchronous Firecrawl in async context** — `asyncio.to_thread(self._firecrawl_search, query)` wraps sync code, but the sync code itself does network I/O. | Thread pool exhaustion |
| **P2-6** | **BM25 only on statutory index** — case law index has no BM25 component, limiting hybrid search quality for judgments. | Lower case law recall |
| **P2-7** | **No health check for Groq** — health endpoint checks Ollama but not Groq availability. | Incomplete monitoring |
| **P2-8** | **Frontend has no error boundary components** — React errors crash the entire UI. | Poor UX |
| **P2-9** | **Two static UI codebases** — `static/index.html` (legacy) and `frontend/` (React). Legacy UI is still mounted. | Confusion |
| **P2-10** | **Metrics are in-memory only** — `MetricsCollector` uses `defaultdict` in memory. Server restart loses all metrics. | No persistent observability |

---

## 11. File Map

```
JustiAssist/
├── app.py                    # Main FastAPI app (2547 lines, monolith)
├── config.py                 # Configuration, dataset discovery, enums
├── vector_store.py           # FAISS + BM25 dual vector store
├── data_loader.py            # Auto-discovery CSV/JSON loader
├── chunker.py                # Domain-aware text chunking
├── llm_provider.py           # Groq + Ollama LLM provider with cache
├── reranker.py               # Legal-specific two-stage reranker
├── context_builder.py        # Evidence-aware context structuring
├── confidence_scorer.py      # Multi-factor retrieval confidence
├── citation_validator.py     # Pre-response citation validation
├── document_session.py       # In-memory uploaded document manager
├── audit_logger.py           # JSONL audit logging
├── metrics.py                # In-memory metrics collection
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── justiassist.db            # SQLite database (users, chat)
│
├── agents/
│   ├── __init__.py
│   ├── query_classifier.py   # LLM + keyword query classification
│   ├── query_reformulator.py # Rule-based query expansion
│   ├── bail_evaluator.py     # Bail assessment (heuristics + LLM)
│   ├── feedback_evaluator.py # Grounding validation
│   ├── crew_orchestrator.py  # Main pipeline coordinator
│   └── tools/                # DEAD CODE (CrewAI tools, Python 3.14 incompatible)
│       ├── firecrawl_tool.py
│       ├── kanoon_tool.py
│       └── vector_search_tool.py
│
├── services/
│   ├── auth.py               # JWT + bcrypt authentication
│   ├── database.py           # SQLAlchemy models + SQLite
│   ├── chat_memory.py        # Chat history CRUD
│   ├── indian_kanoon.py      # Indian Kanoon API client
│   ├── news_scraper.py       # GNews legal news
│   ├── hybrid_retriever.py   # Partially-integrated hybrid retriever
│   └── pipeline_events.py    # SSE event emitter
│
├── prompts/
│   └── templates.py          # System prompts, grounding rules
│
├── data/                     # Small / secondary datasets (29 files)
│   └── kanoon_cache/         # Indian Kanoon API cache (46 JSON files)
│
├── project datasets/         # Full production datasets
│   ├── csv datasets/         # 6 large CSVs (~11.6 MB total)
│   └── json datasets/        # 6 large JSONs (~15.7 MB total)
│
├── vector_stores/
│   ├── statutory/            # FAISS index + BM25 + metadata (~156 MB)
│   └── case_law/             # FAISS index + metadata (~206 MB)
│
├── frontend/                 # React + Vite app
│   └── src/
│       ├── App.jsx           # Main app with tab navigation
│       ├── api.js            # Auth-aware fetch, SSE, chat memory APIs
│       ├── components/       # 21 React components
│       ├── context/          # AuthContext
│       └── pages/            # AuthPage
│
├── static/                   # Legacy HTML UI (mounted at /static)
├── evaluation/               # Offline evaluation harness
├── tests/                    # 9 test files (4 pytest-compatible)
├── logs/                     # JSONL audit logs
└── draft_templates/          # Legal document templates (1 file)
```
