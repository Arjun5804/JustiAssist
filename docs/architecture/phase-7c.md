# Phase 7C: Persistent Chat & Session Storage

## Overview
JustiAssist has hardened its conversation persistence to be production-safe and isolated by user. The system differentiates between `conversation_id` (a stable identifier for an entire thread of chat) and `session_id` (a linkage identifier for uploaded document sessions).

## Current Persistence Flow
1. **User Query:** The client invokes `/query` or `/api/query/stream`, optionally supplying `conversation_id` and/or `session_id`.
2. **Conversation Threading:** If `conversation_id` is supplied, it is validated for ownership. If omitted, a new UUID is generated. 
3. **User Message Storage:** The user's prompt is saved synchronously using `save_message`. 
4. **Duplicate Suppression:** `save_message` implements a best-effort 2-second lookback to suppress duplicate identical writes for the same user prompt in the same conversation.
5. **Orchestrator Execution:** The `AgentOrchestrator` generates the response.
6. **Assistant Message Storage:** Upon successful completion, the assistant's final answer, query type, citations, confidence score, and grounding status are saved identically to the user message. (Streamed tokens are NOT individually saved).

## Conversation Ownership Model
Every `ChatMessage` belongs to a specific `user_id`. 
* Retrieving history implicitly filters by `user_id`.
* Deleting history targets only `user_id` messages.
* `save_message` explicitly raises `ConversationOwnershipError` if a user attempts to save a message to a `conversation_id` already owned by a different user.

## Transaction & Session Boundaries
SQLAlchemy sessions are strictly short-lived. They are created when database I/O is necessary and closed via a `finally` block before yielding back to the network or LLM operations. Database `commit()` calls are now wrapped in `try...except Exception: db.rollback()` to prevent orphaned transactions.

## Tests Added
A dedicated unit test suite (`tests/unit/test_chat_memory.py`) was implemented covering:
* Basic persistence of both user and assistant roles
* Conversation thread continuity
* Strict isolation (preventing User A from reading/writing User B's threads)
* Chronological history retrieval and pagination
* Accurate "Recent Conversations" listing (chronologically first message preview)
* Exact differentiation between `session_id` and `conversation_id`
* Exception-triggered database rollbacks

## Database Schema & Migrations
No schema modifications were required. The existing SQLite / Alembic architecture from Phase 7B remains entirely sufficient.

## Known Limitations
* **Deduplication:** The 2-second identical prompt duplicate suppression is a best-effort check, not true strict transaction idempotency.
