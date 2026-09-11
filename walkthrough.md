# JustiAssist: Complete System Architecture & Walkthrough

## Executive Summary

**JustiAssist** is an intelligent RAG (Retrieval-Augmented Generation) system for Indian legal domain, specializing in bail jurisprudence. It combines:
- **Hybrid Search** (FAISS semantic + BM25 keyword)
- **Multi-Agent Query Processing**
- **Document Upload & Analysis**
- **Confidence-Based Fallback** to GPT-4

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    index.html (Modern Glass UI)                      │    │
│  │  • Mode Selector (Auto/Legal/Bail)                                   │    │
│  │  • Multi-file Document Upload                                        │    │
│  │  • Response Display with Citations                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     app.py (FastAPI Server)                          │    │
│  │  Endpoints: /query, /upload-document, /session/*, /health           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│   QUERY PROCESSING   │ │   RETRIEVAL LAYER    │ │  CONTEXT & CONFIDENCE│
│ ┌──────────────────┐ │ │ ┌──────────────────┐ │ │ ┌──────────────────┐ │
│ │ QueryClassifier  │ │ │ │   VectorStore    │ │ │ │  ContextBuilder  │ │
│ │ (LLM + Keywords) │ │ │ │ (FAISS + BM25)   │ │ │ │ (Evidence Group) │ │
│ └──────────────────┘ │ │ └──────────────────┘ │ │ └──────────────────┘ │
│ ┌──────────────────┐ │ │ ┌──────────────────┐ │ │ ┌──────────────────┐ │
│ │QueryReformulator │ │ │ │  LegalReranker   │ │ │ │ConfidenceScorer  │ │
│ │(Legal Expansion) │ │ │ │ (Section-Aware)  │ │ │ │ (Multi-Factor)   │ │
│ └──────────────────┘ │ │ └──────────────────┘ │ │ └──────────────────┘ │
└──────────────────────┘ └──────────────────────┘ └──────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESPONSE GENERATION                                  │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐  │
│ │  BailEvaluator   │ │   LLMProvider    │ │  FeedbackEvaluator           │  │
│ │ (Specialized)    │ │ (LiteLLM/Groq)   │ │  (Grounding Check)           │  │
│ └──────────────────┘ └──────────────────┘ └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DATA LAYER                                       │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐  │
│ │    DataLoader    │ │   TextChunker    │ │    DocumentSession           │  │
│ │ (Auto-Discovery) │ │ (Domain-Aware)   │ │    (User Uploads)            │  │
│ └──────────────────┘ └──────────────────┘ └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File-by-File Breakdown

### 1. Core Application

#### `app.py` (1097 lines) - FastAPI Server
**Purpose**: The main entry point and API orchestrator.

**Key Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve main UI |
| `/query` | POST | Process legal/bail query |
| `/upload-document` | POST | Upload & analyze document |
| `/session/{id}/documents` | DELETE | Clear session documents |
| `/health` | GET | Health check |

**Query Processing Flow**:
1. Receive query → Classify (bail vs legal info)
2. Reformulate with legal terms
3. Hybrid search (BM25 + semantic)
4. Rerank results
5. Build structured context
6. Score confidence
7. Generate response (grounded or fallback)
8. Validate citations

---

### 2. Configuration

#### `config.py` (9479 bytes) - Central Configuration
**Purpose**: All system constants and environment loading.

**Key Configurations**:
- `LLM_PROVIDER`: litellm_proxy, groq, openai, ollama
- `EMBEDDING_MODEL`: all-MiniLM-L6-v2
- `CHUNK_SIZE`, `CHUNK_OVERLAP`: Domain-specific
- `RETRIEVAL_CONFIDENCE_THRESHOLD`: 0.65 for grounded mode
- Dataset paths and auto-discovery

---

### 3. Data Ingestion Layer

#### `data_loader.py` (570 lines) - Dataset Discovery & Parsing
**Purpose**: Auto-discovers and parses all legal datasets.

**Supported Formats**:
- CSV: IPC sections, CrPC, BNS, Judgments
- JSON: Constitution QA, IndicLegalQA, Indian Laws

**Key Classes**:
- `LegalDocument`: Dataclass for parsed documents
- `DataLoader`: Auto-discovery and format-specific parsing

#### `chunker.py` (395 lines) - Domain-Aware Chunking
**Purpose**: Splits documents into retrieval-optimized chunks.

**Key Features**:
- Token-based chunking (tiktoken)
- Sentence boundary preservation
- Domain-specific chunk sizes:
  - Statutory: 400 tokens
  - Case Law: 600 tokens
  - QA: 300 tokens
- `ContextTrimmer`: Trims context to fit LLM limits

---

### 4. Retrieval Layer

#### `vector_store.py` (513 lines) - Hybrid Search Engine
**Purpose**: FAISS + BM25 hybrid search with dual indices.

**Architecture**:
```
Query ──┬──> Semantic (FAISS) ──> 0.6 weight ──┐
        │                                       ├──> Score Fusion ──> Ranked Results
        └──> Keyword (BM25) ───> 0.4 weight ───┘
```

**Key Methods**:
- `build_statutory_index()`: Laws, sections, QA
- `build_case_law_index()`: Judgments, precedents
- `hybrid_search_statutory()`: Combined search
- `search_bail()`: Case law search

#### `reranker.py` (10541 bytes) - Legal-Specific Reranking
**Purpose**: Second-stage reranking with legal signals.

**Reranking Factors**:
1. Section match boost (3.0x for exact match)
2. Law type boosting (IPC > BNS for older queries)
3. Priority scoring for bail provisions

---

### 5. Agent Layer

#### `agents/query_classifier.py` (142 lines) - Query Classification
**Purpose**: Routes queries to correct pipeline.

**Classification Method**:
1. **LLM-based** (primary): Semantic understanding
2. **Keyword-based** (fallback): Pattern matching

**Categories**:
- `BAIL_QUERY`: Release from custody, bail applications
- `LEGAL_INFO`: Law definitions, punishments, procedures

#### `agents/query_reformulator.py` (14823 bytes) - Query Enhancement
**Purpose**: Expands queries with legal terminology.

**Key Features**:
- Section number extraction (IPC 302 → IPC_302)
- Synonym expansion (murder → homicide, culpable)
- Search term generation

#### `agents/bail_evaluator.py` (19722 bytes) - Bail Assessment Agent
**Purpose**: Specialized bail likelihood assessment.

**Processing Flow**:
```
Bail Query ──┬──> Rule-Based Analysis ──> Bailable/Non-bailable ──┐
             │                                                     ├──> Combine ──> BailEvaluation
             └──> LLM Analysis ────────> Likelihood + Reasoning ──┘
                                                │
                                                ▼
                              (Override if LLM finds "Granted")
```

**Key Features**:
- Bailable/non-bailable classification
- Punishment severity scoring
- CrPC section matching (436-439)
- User document evidence integration

#### `agents/feedback_evaluator.py` (16626 bytes) - Grounding Check
**Purpose**: Post-generation citation validation.

**Validation Checks**:
- Are cited sections in context?
- Are punishment durations accurate?
- Is there hallucination of fabricated provisions?

---

### 6. Context & Confidence

#### `context_builder.py` (398 lines) - Evidence-Aware Context
**Purpose**: Structures retrieved chunks for LLM prompts.

**Grouping Logic**:
1. Statutory provisions (IPC, CrPC, BNS)
2. Case law (Supreme Court, High Court)
3. User-uploaded evidence (marked non-statutory)

**Contradiction Detection**: Flags conflicting punishment terms.

#### `confidence_scorer.py` (414 lines) - Multi-Factor Confidence
**Purpose**: Determines if retrieval is sufficient for grounded response.

**Confidence Factors**:
| Factor | Weight | Description |
|--------|--------|-------------|
| Section Coverage | 0.35 | Are requested sections found? |
| Intent Matching | 0.25 | Do chunks match query concepts? |
| Source Redundancy | 0.15 | Multiple sources agreeing? |
| Legal Completeness | 0.15 | Required bail provisions present? |
| Avg Relevance | 0.10 | Mean similarity score |

**Response Modes**:
- `GROUNDED` (>0.65): Answer from context only
- `FALLBACK` (<0.65): Use GPT-4 with transparency warning

---

### 7. LLM Integration

#### `llm_provider.py` (360 lines) - Unified LLM Interface
**Purpose**: Abstract interface for multiple LLM providers.

**Supported Providers**:
1. LiteLLM Proxy (primary)
2. Groq (fallback)
3. OpenAI
4. Ollama (local)

**Answer Modes**:
- `GROUNDED`: Strict citation enforcement
- `FALLBACK`: General knowledge with warning

---

### 8. Document Session

#### `document_session.py` (421 lines) - User Upload Management
**Purpose**: Session-scoped document storage with FAISS indexing.

**Key Features**:
- Per-session isolation (1-hour timeout)
- Document chunking and indexing
- Search within uploaded documents
- Clear/delete document management

**Critical Constraint**: Uploaded documents are NEVER statutory law.

---

### 9. Prompts

#### `prompts/templates.py` (13186 bytes) - Prompt Templates
**Purpose**: System prompts and response formatting.

**Key Templates**:
- `LEGAL_SYSTEM_PROMPT`: Grounding rules for legal info
- `BAIL_SYSTEM_PROMPT`: Structured bail assessment format
- `UPLOADED_DOCUMENT_RULES`: Non-statutory evidence handling

---

### 10. Observability

#### `audit_logger.py` (3837 bytes) - Structured Logging
**Purpose**: JSON-structured audit trail for debugging.

#### `metrics.py` (3796 bytes) - Production Metrics
**Purpose**: Query counts, latency tracking, error rates.

#### `citation_validator.py` (5587 bytes) - Citation Verification
**Purpose**: Validates cited sections exist in context.

---

### 11. Frontend

#### `static/index.html` (474 lines) - Main UI
**Purpose**: Modern glass-morphism interface.

**Features**:
- Mode selector (Auto/Legal/Bail)
- Query input with bail-specific options
- Multi-file document upload
- Response display with citations
- Confidence meter and grounding status

#### `static/style.css` (824 lines) - UI Styling
**Purpose**: Dark theme with gradients and animations.

---

## End-to-End Query Flow

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  1. API Layer (app.py)                                      │
│     POST /query {query: "Can I get bail for IPC 302?"}     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Query Classification (QueryClassifier)                   │
│     LLM determines: BAIL_QUERY                              │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Query Reformulation (QueryReformulator)                  │
│     Enhanced: "bail IPC 302 murder CrPC 437 438"            │
│     Extracted sections: [IPC_302, CrPC_437, CrPC_438]       │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Hybrid Search (VectorStore)                              │
│     FAISS (0.6) + BM25 (0.4) → 15 raw results               │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Reranking (LegalReranker)                                │
│     Section boost + Law type boost → 8 filtered results     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Context Building (ContextBuilder)                        │
│     Group by: Statutory → Case Law → User Docs              │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Confidence Scoring (ConfidenceScorer)                    │
│     Score: 0.78 → Mode: GROUNDED                            │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  8. Bail Evaluation (BailEvaluator)                          │
│     Rule-based: Non-bailable, Severity 9/10                 │
│     LLM Analysis: Structured assessment with precedents     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  9. Response Validation (FeedbackEvaluator)                  │
│     Grounding check: PASS                                   │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  10. API Response                                            │
│      {answer, citations, bail_assessment, confidence: 0.78} │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Hybrid Search (FAISS + BM25)
**Why**: Legal queries often contain exact section numbers (e.g., "IPC 302"). Pure semantic search may miss these. BM25 ensures exact matches are found.

### 2. Dual Indices (Statutory vs Case Law)
**Why**: Statutory law (IPC, CrPC) is authoritative. Case law is precedent. Never mixing ensures correct citation hierarchy.

### 3. Confidence-Based Fallback
**Why**: RAG fails when retrieved context is insufficient. Instead of refusing, we transparently use GPT-4's general knowledge with a warning.

### 4. User Document as Non-Statutory
**Why**: Uploaded FIRs and judgments provide case context, but are not law. Explicit tagging prevents the LLM from citing them as authority.

### 5. LLM-Based Query Classification
**Why**: Keyword matching fails for colloquial queries like "my friend is in jail". LLM understands intent semantically.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | FastAPI |
| Vector Database | FAISS (Meta) |
| Keyword Search | rank-bm25 |
| Embeddings | Sentence-Transformers (MiniLM-L6-v2) |
| LLM Integration | LiteLLM (proxy support) |
| Primary LLM | Groq (Llama 3.1/3) |
| Fallback LLM | GPT-4 via LiteLLM Proxy |
| Frontend | Vanilla JS + CSS |
| Document Parsing | PyMuPDF, python-docx |

---

## Summary

JustiAssist is a production-ready legal AI system with:
- **16 core Python modules** handling everything from data ingestion to response validation
- **4 specialized agents** for query classification, reformulation, bail evaluation, and grounding
- **Hybrid retrieval** combining semantic and keyword search
- **Confidence-aware generation** with transparent fallback
- **Session-based document management** with proper evidence handling

The system is designed for accuracy, transparency, and legal domain specificity.
