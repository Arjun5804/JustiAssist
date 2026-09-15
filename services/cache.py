import json
import logging
import asyncio
from typing import Optional, Any
from config import settings

logger = logging.getLogger(__name__)

class CacheService:
    """
    Lightweight, application-owned Redis abstraction for JustiAssist.
    Implements a lock-free cache-aside pattern with graceful degradation.
    """
    
    def __init__(self):
        self.enabled = getattr(settings, "REDIS_ENABLED", False)
        self.redis = None
        self.default_ttl = getattr(settings, "REDIS_DEFAULT_TTL", 3600)
        
    async def init(self):
        """Initialize Redis connection pool if enabled."""
        if not self.enabled:
            logger.info("Redis cache is DISABLED via configuration.")
            return
            
        try:
            import redis.asyncio as redis
            self.redis = redis.from_url(
                getattr(settings, "REDIS_URL", "redis://localhost:6379"),
                decode_responses=True
            )
            # We don't await a ping here so that startup doesn't fail if Redis is temporarily down.
            # redis.asyncio creates connections lazily on first command.
            logger.info("Redis cache initialized (lazy connection).")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}. Caching will gracefully degrade to no-op.")
            self.redis = None

    async def close(self):
        """Close the Redis connection pool."""
        if self.redis:
            try:
                await self.redis.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")

    async def get(self, key: str) -> Optional[Any]:
        """
        Fetch and deserialize JSON from cache.
        Returns None on cache miss, connection error, or malformed JSON.
        """
        if not self.enabled or not self.redis:
            return None
            
        try:
            val = await self.redis.get(key)
            if val is None:
                return None
                
            try:
                return json.loads(val)
            except json.JSONDecodeError as e:
                logger.warning(f"Malformed JSON in cache for key {key}: {e}. Treating as cache miss.")
                # We could delete the malformed key here, but it's safer to just return None
                # and let it be overwritten or expire.
                return None
        except Exception as e:
            logger.warning(f"Redis GET failed for key {key}: {e}. Degrading to cache miss.")
            return None

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        """
        Serialize to JSON and set with explicit TTL.
        Fails silently on connection errors to avoid disrupting application flow.
        """
        if not self.enabled or not self.redis:
            return
            
        _ttl = ttl if ttl is not None else self.default_ttl
        
        try:
            serialized_value = json.dumps(value)
            await self.redis.setex(key, _ttl, serialized_value)
        except Exception as e:
            logger.warning(f"Redis SET failed for key {key}: {e}. Continuing normally.")

    async def delete(self, key: str) -> None:
        """
        Delete key from cache.
        Fails silently on connection errors.
        """
        if not self.enabled or not self.redis:
            return
            
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Redis DELETE failed for key {key}: {e}. Continuing normally.")

# Singleton instance
cache = CacheService()
