# Phase 10D Implementation Plan

## Goal
Implement the minimal production-reliability fixes identified in the Phase 10D Audit, particularly focusing on SSE lifecycle management, external retrieval hard timeouts, and LLM retry bounding, while ensuring cancellation propagates safely.

## Proposed Changes

### 1. SSE Background Task Cancellation (`api/query.py`)
- **[MODIFY]** `api/query.py`: Wrap the SSE `while True: msg = await queue.get()` loop in a `try...finally` block.
- In the `finally` block, check `if not task.done(): task.cancel()`.
- Wait for the task safely:
  ```python
  try:
      await task
  except asyncio.CancelledError:
      pass
  except Exception as e:
      logger.error(f"Error during SSE task cancellation: {e}", exc_info=True)
  ```
- Ensure `run_orchestrator()` propagates `asyncio.CancelledError`.

### 2. Firecrawl Hard Timeout (`retrieval/external.py`)
- **[MODIFY]** `retrieval/external.py`: Wrap the synchronous thread dispatch `await asyncio.to_thread(service.search, query)` in `asyncio.wait_for(..., timeout=10.0)`.
- Catch `asyncio.TimeoutError` and gracefully return `[]` without leaking exceptions.

### 3. Legal News / GNews Hard Timeout (`retrieval/external.py`)
- **[MODIFY]** `retrieval/external.py`: Wrap `await asyncio.to_thread(scraper.fetch_news, news_query)` in `asyncio.wait_for(..., timeout=10.0)`.
- Catch `asyncio.TimeoutError` and gracefully return `[]`. This naturally respects the `is_fallback` filter while avoiding hangs.

### 4. LLM Retry / Feedback Loop Bound (`llm_provider.py` & `generation/pipeline.py`)
- **[VERIFY]** `llm_provider.py`: No changes needed as Groq internal retries are strictly 3 (`MAX_RETRIES`), and fallback to Ollama is a one-shot process. `asyncio.CancelledError` safely bubbles up through `Exception` block bypass.
- **[VERIFY]** `generation/pipeline.py`: No changes needed as `max_retries` is enforced as 2.

### 5. Regression Tests (`tests/unit/test_reliability.py`)
- **[NEW]** `tests/unit/test_reliability.py`: Implement the 19 required test cases using pytest and `unittest.mock`. 
- Group the tests by SSE, Firecrawl, GNews, LLM Retry Bounds, and Cancellation.
- Mock all network components (`LLMProvider`, `FirecrawlService`, `LegalNewsScraper`).

### 6. Documentation (`docs/architecture/phase-10d.md`)
- **[NEW]** `docs/architecture/phase-10d.md`: Create documentation capturing implemented fixes, timeout matrix, and explicitly deferred 10E/10F work.

## Verification Plan
1. `python -m pytest tests/unit/test_reliability.py -q`
2. `alembic check`
3. `npm run build && npm run lint` in `frontend/`
4. Confirm `docs: add phase 10d reliability audit` commit is preserved.
5. Create exactly one commit `fix: harden reliability and error handling`.

## User Review Required
None of these changes touch database, frontend, or observability. Please approve this plan.
