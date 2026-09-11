"""
JustiAssist LLM Provider — Groq-Native with Ollama Fallback
"""

import os
import asyncio
import hashlib
import time
import logging
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    AnswerMode,
    DEFAULT_ANSWER_MODE,
    RETRIEVAL_CONFIDENCE_THRESHOLD,
    ANSWER_MODE_LABELS,
    INSUFFICIENT_CONTEXT_RESPONSE
)

logger = logging.getLogger(__name__)


# ==================== Response Cache ====================

class LRUCache:
    """Simple in-memory LRU cache for LLM responses."""
    
    def __init__(self, max_size: int = 64, ttl_seconds: int = 120):
        self._cache: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
    
    def _make_key(self, prompt: str, model: str) -> str:
        return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()
    
    def get(self, prompt: str, model: str) -> Optional[str]:
        key = self._make_key(prompt, model)
        if key in self._cache:
            text, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                self._cache.move_to_end(key)
                return text
            else:
                del self._cache[key]
        return None
    
    def put(self, prompt: str, model: str, response: str):
        key = self._make_key(prompt, model)
        self._cache[key] = (response, time.time())
        self._cache.move_to_end(key)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


# Singleton cache
_response_cache = LRUCache()


# ==================== LLM Provider ====================

class LLMProvider:
    """
    Groq-native LLM provider with Ollama local fallback.
    
    Priority:
    1. Groq Cloud (primary) — fast inference, llama-3.3-70b-versatile
    2. Ollama Local (fallback) — runs when Groq is unavailable
    """
    
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    TIMEOUT = 45.0    # seconds
    
    def __init__(self):
        self._groq_client = None
        self._setup_groq()
    
    def _setup_groq(self):
        """Initialize Groq async client."""
        if GROQ_API_KEY:
            try:
                from groq import AsyncGroq
                self._groq_client = AsyncGroq(
                    api_key=GROQ_API_KEY,
                    timeout=self.TIMEOUT
                )
                logger.info(f"Groq client initialized (model: {GROQ_MODEL})")
            except ImportError:
                logger.warning("groq package not installed. Install with: pip install groq")
        else:
            logger.warning("GROQ_API_KEY not set. Will use Ollama fallback only.")
    
    async def generate(
        self,
        prompt: str,
        answer_mode: AnswerMode = DEFAULT_ANSWER_MODE,
        retrieval_scores: list = None,
        temperature: float = None,
        max_tokens: int = None,
        use_cache: bool = True,
    ) -> Tuple[str, AnswerMode, Dict[str, Any]]:
        """
        Generate a response. Tries Groq first, falls back to Ollama.
        """
        # Determine answer mode
        actual_mode = answer_mode
        if retrieval_scores:
            avg_score = sum(retrieval_scores) / len(retrieval_scores)
            if avg_score < RETRIEVAL_CONFIDENCE_THRESHOLD:
                actual_mode = AnswerMode.FALLBACK
        elif retrieval_scores is not None and len(retrieval_scores) == 0:
            actual_mode = AnswerMode.FALLBACK
        
        system_message = self._get_system_message(actual_mode)
        temp = temperature if temperature is not None else LLM_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else LLM_MAX_TOKENS
        
        # Check cache
        if use_cache:
            cached = _response_cache.get(prompt, GROQ_MODEL)
            if cached:
                logger.info("[LLM] Cache hit")
                return cached, actual_mode, {"model": GROQ_MODEL, "source": "cache"}
        
        metadata = {"answer_mode": actual_mode.value, "temperature": temp}
        
        # 1. Try Groq
        if self._groq_client:
            try:
                response_text = await self._call_groq(
                    system_message, prompt, temp, tokens
                )
                metadata["model"] = GROQ_MODEL
                metadata["source"] = "groq"
                
                # Cache it
                if use_cache:
                    _response_cache.put(prompt, GROQ_MODEL, response_text)
                
                # Add fallback label if needed
                if actual_mode == AnswerMode.FALLBACK:
                    label = ANSWER_MODE_LABELS.get(AnswerMode.FALLBACK)
                    if label:
                        response_text = f"{label}\n\n{response_text}"
                
                return response_text, actual_mode, metadata
                
            except Exception as e:
                logger.warning(f"Groq failed after retries: {e}. Falling back to Ollama.")
        
        # 2. Fallback to Ollama
        try:
            response_text = await self._call_ollama(
                system_message, prompt, temp, tokens
            )
            metadata["model"] = OLLAMA_MODEL
            metadata["source"] = "ollama"
            
            if actual_mode == AnswerMode.FALLBACK:
                label = ANSWER_MODE_LABELS.get(AnswerMode.FALLBACK)
                if label:
                    response_text = f"{label}\n\n{response_text}"
            
            return response_text, actual_mode, metadata
            
        except Exception as e:
            error_msg = f"All LLM providers failed. Groq and Ollama both unavailable. Error: {e}"
            logger.error(error_msg)
            return error_msg, actual_mode, {"error": str(e)}
    
    async def _call_groq(
        self, system_msg: str, prompt: str, temperature: float, max_tokens: int
    ) -> str:
        """Call Groq with retry + exponential backoff."""
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
                
            except Exception as e:
                last_error = e
                wait = self.BASE_DELAY * (2 ** attempt)
                logger.warning(f"Groq attempt {attempt+1}/{self.MAX_RETRIES} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
        
        raise last_error
    
    async def _call_ollama(
        self, system_msg: str, prompt: str, temperature: float, max_tokens: int
    ) -> str:
        """Call local Ollama as fallback."""
        import httpx
        
        full_prompt = f"{system_msg}\n\n{prompt}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }
            )
            response.raise_for_status()
            return response.json().get("response", "")
    
    def _get_system_message(self, mode: AnswerMode) -> str:
        if mode == AnswerMode.GROUNDED:
            return """You are JustiAssist, an AI legal assistant specialized in Indian criminal law.

STRICT RULES FOR GROUNDED MODE:
1. Answer ONLY using the provided context
2. If the context does not contain sufficient information, say so explicitly
3. NEVER fabricate legal provisions, section numbers, or case citations
4. Always cite specific sections or sources from the context
5. If uncertain, acknowledge it explicitly

Your response must be 100% grounded in the provided context."""

        else:
            return """You are JustiAssist, an AI legal assistant specialized in Indian criminal law.

FALLBACK MODE ACTIVE:
The retrieval system found no relevant context, OR confidence is low.
You may answer using general legal knowledge, but:
1. CLEARLY state this is general knowledge
2. Be conservative in your claims
3. Recommend consulting a qualified advocate
4. Do NOT fabricate specific section numbers unless certain"""


# ==================== Convenience Functions ====================

# Singleton provider
_provider_instance: Optional[LLMProvider] = None

def _get_provider() -> LLMProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = LLMProvider()
    return _provider_instance


async def call_llm(
    prompt: str,
    answer_mode: AnswerMode = DEFAULT_ANSWER_MODE,
    retrieval_scores: list = None,
    temperature: float = None,
    max_tokens: int = None,
) -> str:
    """
    Primary async LLM call. Used by all endpoints and agents.
    Returns just the response text.
    """
    provider = _get_provider()
    response_text, _, _ = await provider.generate(
        prompt,
        answer_mode,
        retrieval_scores,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response_text


async def call_llm_full(
    prompt: str,
    answer_mode: AnswerMode = DEFAULT_ANSWER_MODE,
    retrieval_scores: list = None,
    temperature: float = None,
    max_tokens: int = None,
) -> Tuple[str, AnswerMode, Dict[str, Any]]:
    """
    Full async LLM call returning (text, mode, metadata).
    """
    provider = _get_provider()
    return await provider.generate(
        prompt,
        answer_mode,
        retrieval_scores,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm_sync(
    prompt: str,
    answer_mode: AnswerMode = DEFAULT_ANSWER_MODE,
    retrieval_scores: list = None,
) -> str:
    """Synchronous LLM call (for non-async contexts)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = loop.run_in_executor(
                pool,
                lambda: asyncio.run(call_llm(prompt, answer_mode, retrieval_scores))
            )
            return result
    except RuntimeError:
        return asyncio.run(call_llm(prompt, answer_mode, retrieval_scores))


if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing Groq-native LLM Provider...")
        result = await call_llm("What is Section 302 of IPC?")
        print(f"Response: {result[:300]}...")
    
    asyncio.run(test())
