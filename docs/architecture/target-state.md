# JustiAssist — Target Architecture

> **Phase 0A** | Generated 2026-09-11 | For reference only — no implementation yet

---

## 1. Design Goals

1. **Modular monolith** — decompose the 2,547-line `app.py` into focused modules with clear boundaries, without prematurely introducing microservices
2. **Testable** — every component independently testable with mocks, no full vector store required for unit tests
3. **Single pipeline** — eliminate the duplicate legacy/v2 pipeline; one code path for all queries
4. **Reliable** — structured error handling, retries, circuit breakers for external APIs
5. **Observable** — structured logging, persistent metrics, request tracing
6. **Secure** — secrets management, rate limiting, CORS hardening

---

## 2. Target Module Structure

```
JustiAssist/
├── app.py                        # Slim entry point: FastAPI app + lifespan only (~100 lines)
├── config.py                     # Configuration (largely unchanged)
│
├── api/                          # Route handlers (extracted from app.py)
│   ├── __init__.py
│   ├── query.py                  # /api/v2/query, /api/v2/query/stream
│   ├── auth.py                   # /api/auth/*
│   ├── chat.py                   # /api/chat/*
│   ├── documents.py              # /upload-document, /session/*
│   ├── features.py               # /api/predict/case, /api/counter-arguments, etc.
│   ├── kanoon.py                 # /api/kanoon/*
│   ├── admin.py                  # /build-indices, /stats, /metrics, /health
│   └── middleware.py             # CORS, rate limiting, request ID injection
│
├── agents/                       # Agent logic (refined)
│   ├── __init__.py
│   ├── classifier.py             # QueryClassifier
│   ├── reformulator.py           # QueryReformulator
│   ├── bail_evaluator.py         # BailEvaluator
│   ├── grounding_evaluator.py    # FeedbackEvaluator + CitationValidator merged
│   └── orchestrator.py           # Pipeline coordinator (crew_orchestrator simplified)
│
├── retrieval/                    # Retrieval subsystem (extracted)
│   ├── __init__.py
│   ├── vector_store.py           # FAISS + BM25
│   ├── reranker.py               # LegalReranker
│   ├── context_builder.py        # ContextBuilder
│   ├── confidence.py             # ConfidenceScorer
│   └── chunker.py                # TextChunker
│
├── services/                     # External integrations
│   ├── llm.py                    # LLMProvider
│   ├── kanoon.py                 # IndianKanoonAPI
│   ├── news.py                   # LegalNewsScraper
│   ├── firecrawl.py              # Firecrawl web search
│   ├── database.py               # SQLAlchemy models (no init on import)
│   ├── auth.py                   # JWT + bcrypt
│   └── chat_memory.py            # Chat history CRUD
│
├── prompts/                      # Prompt templates
├── data/                         # Datasets
├── tests/
│   ├── unit/                     # Fast, isolated unit tests
│   ├── integration/              # Tests requiring vector store
│   ├── conftest.py               # Shared fixtures, mocks
│   └── evaluation/               # Offline eval harness
└── docs/
    └── architecture/
```

---

## 3. Key Architectural Changes

### 3.1 Pipeline Unification

- Remove legacy `/query` and `/api/query/stream` endpoints
- Single pipeline through `orchestrator.process_query()`
- All query paths (REST, SSE) go through the same code

### 3.2 Dependency Injection

- Replace global mutable variables with a `Dependencies` container
- Pass dependencies explicitly to handlers and agents
- Enable test isolation via mock dependencies

### 3.3 Structured Error Handling

- Define `JustiAssistError` hierarchy
- External API calls wrapped with retry + circuit breaker
- Typed error responses to frontend

### 3.4 Test Architecture

- `conftest.py` with fixtures for mock vector store, mock LLM, mock DB
- Unit tests for every agent, scorer, validator
- Integration tests for full pipeline (separate test suite)
- Evaluation harness as a proper test module

### 3.5 Observability

- Replace `print()` with structured `logger` calls
- Persistent metrics (file or SQLite backed)
- Request ID propagation through pipeline stages

---

## 4. Migration Strategy

The target state will be reached incrementally:

1. **Phase 0A** (current) — Document, don't change
2. **Phase 0B** — Extract route handlers from app.py → `api/` modules
3. **Phase 1** — Unify pipelines, remove legacy endpoints
4. **Phase 2** — Add unit tests + conftest.py
5. **Phase 3** — Introduce dependency injection
6. **Phase 4** — Structured logging + error handling
7. **Phase 5** — (Future) Consider agentic framework, vector DB, containerization
