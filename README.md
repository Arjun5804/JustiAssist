# JustiAssist v2.0

**Intelligent Legal AI for Indian Bail Jurisprudence**

JustiAssist is an intelligent legal AI system designed to reduce unsupported legal claims through evidence validation and claim verification. It utilizes a hybrid Retrieval-Augmented Generation (RAG) architecture, native Python agent orchestration, and grounded generation to assist with Indian law, particularly bail jurisprudence.

---

## Key Capabilities
* **Hybrid RAG:** Fuses FAISS (dense) and BM25 (sparse) retrieval for high-accuracy context.
* **Reranking:** Leverages cross-encoder models for accurate legal context prioritization.
* **Evidence Validation & Claim Verification:** Actively validates generated claims against retrieved evidence to prevent hallucinations.
* **Grounded Generation:** Ensures answers are strictly derived from authoritative sources.
* **Abstention:** Refuses to answer queries that lack sufficient legal context.
* **Native Agent Orchestration:** Uses purely native Python/Pydantic agents (no CrewAI, LangGraph, or Agno required).

---

## High-Level Architecture

The current Phase 10F architecture represents a robust, single-worker production design:

```
User
  ↓
Frontend (React) / Nginx
  ↓ (SSE / REST)
FastAPI Backend
  ↓
AgentOrchestrator
  ↓
Router ↔ Research ↔ Analysis ↔ Response ↔ Verification
  ↓
RetrievalPipeline
  ↓
FAISS (Dense) + BM25 (Sparse) + Reranking (BGE-M3)
  ↓
Evidence Validation
  ↓
Grounded Generation
  ↓
Claim Verification
  ↓
Final Answer (or Abstention)
```

**Infrastructure Components:**
* **PostgreSQL:** Persistent application metadata (users, chat messages, document metadata).
* **Redis:** Caching and atomic Lua-based rate limiting (Optional fail-open dependency).
* **Local Object Storage:** Persistent storage for uploaded document bytes.
* **External Evidence Providers:** Firecrawl, Indian Kanoon, and News APIs (governed and controlled).

---

## Core RAG Pipeline

JustiAssist strictly differentiates between *retrieval relevance*, *claim support*, and *legal correctness*. 

1. **Hybrid Fusion:** Combines FAISS dense retrieval and BM25 sparse retrieval to maximize recall.
2. **Reranking:** A legal reranker evaluates and prioritizes the retrieved context.
3. **ContextBuilder:** Constructs a strict context payload segregating authoritative (statutory/case law) and non-authoritative (user uploads) evidence.
4. **Evidence Validation & Claim Verification:** Evaluates the generated claims against the retrieved evidence, mapping specific claims to their provenance.
5. **Grounded Generation & Abstention:** Generates responses derived exclusively from the provided context. If the context is insufficient, the system abstains.

---

## Agent Architecture

JustiAssist utilizes a native Python agent orchestration model built on strict Pydantic contracts. It does not rely on third-party orchestration frameworks.

The flow is managed by the `AgentOrchestrator`, which delegates responsibilities across specialized agent classes:
* **QueryClassifier:** Determines query intent (statutory, case law, bail).
* **QueryReformulator:** Expands and rewrites queries for optimal retrieval.
* **BailEvaluator:** Specifically evaluates bail-related queries and conditions.
* **FeedbackEvaluator:** Performs post-generation verification and quality checks.

---

## External Evidence Governance

External evidence from Firecrawl, Indian Kanoon, and news scrapers is heavily governed. It is strictly categorized by source authority and provenance. External evidence is merged into the overall evidence set and subjected to the same rigorous validation and verification boundaries as local statutory context before final generation. 

*(Note: Full temporal legal reasoning across IPC→BNS / CrPC→BNSS is slated for future work and is not yet fully implemented).*

---

## Persistence and Storage

### PostgreSQL
Used as the primary persistent datastore for:
* User accounts and authentication details.
* Chat messages and conversation history.
* Document metadata.

### Object Storage
* Implements local object storage.
* Stores persistent object bytes for user-uploaded documents securely on disk.

### Redis
* Used for atomic rate limiting and optional caching.
* Strictly an optional dependency; the system degrades gracefully if Redis is unavailable.

### FAISS
* Used exclusively for **local/in-memory** dense vector retrieval indices. JustiAssist does **not** currently use an external vector database.

---

## Important Production Architecture Limitation

The Phase 10F deployment has a known scaling constraint:
* **Single Backend Worker:** Because FAISS indices and the active `DocumentSession` state reside entirely in-process/in-memory, horizontal scaling across multiple backend workers is not currently supported without sticky sessions.
* **State Resets on Restart:** Restarting the backend process will wipe the active in-memory `DocumentSession` state and require reloading the FAISS indices.
* **Persistent Data:** However, PostgreSQL metadata and local object storage bytes *are* persistent and will survive a restart (provided the underlying Docker volume is persistent).

---

## Local Development & Quick Start

For complete instructions on running the application locally using Docker Compose, including health checks, testing, and troubleshooting, please refer to the comprehensive guide:

👉 **[Local Deployment Guide](docs/development/local-deployment.md)**

---

## Technology Stack

* **Backend:** Python 3.11, FastAPI, SQLAlchemy, Alembic, Pydantic, Uvicorn
* **AI/RAG:** FAISS, BM25, HuggingFace (BGE-M3)
* **Datastore:** PostgreSQL 15, Redis 7 (Optional)
* **Frontend:** React, Vite, Nginx
* **Infrastructure:** Docker, Docker Compose

---

## Security

JustiAssist implements robust security mechanisms for a production environment:
* **Authentication:** Secure JWT-based authentication.
* **Streaming Security:** Mandatory single-use SSE tickets for streaming endpoints.
* **Authorization:** Explicit role-based checks for admin routes.
* **Abuse Prevention:** Atomic Lua-based rate limiting via Redis (with graceful fallback).
* **Observability:** ContextVar-based request correlation IDs for complete tracing, without exposing raw secrets in logs.
* **Configuration:** Strict separation of development and production configurations. No secrets are committed to the repository.

---

## Roadmap

* **Phase 0–10:** Completed / Implemented (RAG Pipeline, Agent Orchestration, Document Sessions, Production Hardening).
* **Phase 11:** Admin portal and usage analytics.
* **Phase 12:** Temporal legal reasoning (IPC to BNS translation).

---
