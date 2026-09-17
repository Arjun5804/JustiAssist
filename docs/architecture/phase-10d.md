# Phase 10D: Reliability & Error Handling

## Objectives
Implement the minimal production-reliability fixes identified by the Phase 10D audit, focusing on graceful degradation, bounded execution, and preventing resource leaks.

## Implemented Fixes
1. **SSE Client-Disconnect Cleanup:** In `api/query.py`, wrapped the SSE generator event loop in a `try...finally` block to guarantee the cancellation of the `run_orchestrator()` background task when the client connection drops prematurely. Handled `asyncio.CancelledError` gracefully during cleanup.
2. **Hard Timeouts for External Retrieval:** In `retrieval/external.py`, applied explicit `asyncio.wait_for` barriers with a 10.0-second timeout to the synchronous `FirecrawlApp` and `GNews` operations pushed to background threads via `asyncio.to_thread`. Handled `asyncio.TimeoutError` to prevent thread hangs, reverting to empty collections (triggering local fallback safely without treating hard-coded news fallback items as legitimate evidence).
3. **Bounded LLM Execution Assurance:** Confirmed the bounded nature of `LLMProvider` retries (Max 3 Groq attempts followed by a one-shot Ollama fallback) and `GroundedGenerationPipeline` iteration limits (Max 2 Generation+Verification cycles).
4. **Cancellation Propagation:** Verified that `asyncio.CancelledError` correctly bubbles up through LLM and API layers, properly halting execution without inadvertently triggering retry/fallback mechanisms.

## Timeout / Retry Matrix
The following bounds are explicitly enforced by the system:

| Component     | Operation             | Timeout | Retry | Fallback             |
| ------------- | --------------------- | ---: | ---: | -------------------- |
| Groq          | LLM request           | 45.0s | 3 | Ollama               |
| Ollama        | LLM request           | 60.0s | None | terminal failure     |
| Indian Kanoon | external search       | 3.0s | None | local evidence       |
| Firecrawl     | web search            | 10.0s | None | empty/local evidence |
| GNews         | news retrieval        | 10.0s | None | fallback/cache       |
| SSE           | orchestrator lifetime | client/request lifetime | None | cancellation         |

## Test Suite
Created `tests/unit/test_reliability.py` to assert:
- Correct SSE background task cancellation and cleanup.
- Bounded Firecrawl execution, handling timeouts gracefully.
- Bounded GNews execution, preventing fake fallback contamination on timeouts.
- LLM provider worst-case execution bounds and proper fallback triggers.
- Propagation of `asyncio.CancelledError` without invoking subsequent retry logic.

## Deferred Scope (Phase 10E/10F)
The following tasks are explicitly deferred to later phases as per implementation instructions:
- Broad architectural observability, including Prometheus, OpenTelemetry, tracing, and metrics dashboards.
- Deep architectural rewrites for Redis-based task queues or Celery-based background orchestration.
- Kubernetes deployment configurations and temporal legal reasoning capabilities.
