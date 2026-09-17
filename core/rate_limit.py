
import math
import logging
from typing import Optional, Tuple
from fastapi import Request, HTTPException, Depends

from services.cache import cache
from services.auth import get_current_user_optional, User


logger = logging.getLogger(__name__)

# Atomic Rate-Limiting Lua Script
# KEYS[1]: rate limit key
# ARGV[1]: max requests
# ARGV[2]: window in seconds
# Returns: {current_count, ttl_in_ms}
RATE_LIMIT_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local current = tonumber(redis.call("GET", key) or "0")
if current >= limit then
    return {current + 1, redis.call("PTTL", key)}
end

current = tonumber(redis.call("INCR", key))
if current == 1 then
    redis.call("EXPIRE", key, window)
end
return {current, redis.call("PTTL", key)}
"""

def parse_rate_limit(limit_str: str) -> Tuple[int, int]:
    """Parse a limit string like '5/minute' into (limit, window_seconds)."""
    parts = limit_str.split('/')
    if len(parts) != 2:
        raise ValueError(f"Invalid rate limit format: {limit_str}")
        
    limit = int(parts[0])
    if limit <= 0:
        raise ValueError(f"Rate limit must be a positive integer, got: {limit}")
        
    window_str = parts[1].lower().strip()
    if window_str in ('second', 's'):
        window = 1
    elif window_str in ('minute', 'm'):
        window = 60
    elif window_str in ('hour', 'h'):
        window = 3600
    else:
        raise ValueError(f"Unknown rate limit window unit: {window_str}")
        
    return limit, window

class RateLimitService:
    def __init__(self):
        self._script_sha: Optional[str] = None

    async def _load_script(self) -> Optional[str]:
        if not cache.enabled or not cache.redis:
            return None
        if self._script_sha is None:
            try:
                self._script_sha = await cache.redis.script_load(RATE_LIMIT_LUA)
            except Exception as e:
                logger.warning(f"Failed to load Lua script for rate limiting: {e}")
                return None
        return self._script_sha

    async def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """
        Atomically check and increment rate limit.
        Returns (is_allowed, remaining, retry_after_seconds).
        Fails open if Redis is unavailable.
        """
        if not cache.enabled or not cache.redis:
            return True, limit, 0

        try:
            sha = await self._load_script()
            if not sha:
                return True, limit, 0
                
            try:
                res = await cache.redis.evalsha(sha, 1, key, limit, window)
            except Exception as e:
                if "NOSCRIPT" in str(e):
                    # Reload and retry once
                    self._script_sha = None
                    sha = await self._load_script()
                    if not sha:
                        return True, limit, 0
                    res = await cache.redis.evalsha(sha, 1, key, limit, window)
                else:
                    raise e
                    
            current, ttl_ms = res
            
            # Use math.ceil to ensure we don't round down to 0 seconds while actively blocked
            ttl_seconds = max(1, math.ceil(ttl_ms / 1000.0)) if ttl_ms > 0 else window
            remaining = max(0, limit - current)
            
            if current > limit:
                return False, 0, ttl_seconds
            
            return True, remaining, 0
            
        except Exception as e:
            logger.warning(f"RateLimitService error for key {key}: {e}. Fails open.")
            return True, limit, 0

rate_limit_service = RateLimitService()

def get_client_ip(request: Request) -> str:
    """Safely extract client IP from Nginx X-Real-IP or fallback."""
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else "127.0.0.1"

class RateLimiter:
    """
    FastAPI dependency for rate limiting.
    Extracts identity from authenticated user or fallback to IP.
    """
    def __init__(self, category: str, limit_str: str):
        self.category = category
        self.limit, self.window = parse_rate_limit(limit_str)

    async def __call__(self, request: Request, user: Optional[User] = Depends(get_current_user_optional)):
        if user:
            identity = f"user:{user.id}"
        else:
            identity = f"ip:{get_client_ip(request)}"

        key = f"rate_limit:{self.category}:{identity}"

        is_allowed, remaining, retry_after = await rate_limit_service.is_allowed(
            key=key, limit=self.limit, window=self.window
        )

        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Too Many Requests",
                headers={"Retry-After": str(retry_after)}
            )
