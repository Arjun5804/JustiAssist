import pytest
import time
from unittest.mock import AsyncMock, patch

from core.rate_limit import RateLimitService, parse_rate_limit

def test_parse_rate_limit():
    assert parse_rate_limit("5/minute") == (5, 60)
    assert parse_rate_limit("10/second") == (10, 1)
    assert parse_rate_limit("100/hour") == (100, 3600)
    
    with pytest.raises(ValueError):
        parse_rate_limit("invalid")
    with pytest.raises(ValueError):
        parse_rate_limit("-5/minute")
    with pytest.raises(ValueError):
        parse_rate_limit("5/decade")

@pytest.fixture
def fake_redis():
    class FakeRedis:
        def __init__(self):
            self.scripts = {}
            self.data = {}
            self.ttls = {}
            
        async def script_load(self, script):
            sha = "fake_sha"
            self.scripts[sha] = script
            return sha
            
        async def evalsha(self, sha, numkeys, key, limit, window):
            if sha not in self.scripts:
                raise Exception("NOSCRIPT No matching script. Please use EVAL.")
            
            now = time.time()
            if key in self.ttls and self.ttls[key] <= now:
                del self.data[key]
                del self.ttls[key]
                
            current = self.data.get(key, 0)
            if current >= limit:
                ttl = max(0, int((self.ttls.get(key, now) - now) * 1000))
                return [current + 1, ttl]
                
            current += 1
            self.data[key] = current
            if current == 1:
                self.ttls[key] = now + window
                
            ttl = max(0, int((self.ttls.get(key, now) - now) * 1000))
            return [current, ttl]

    return FakeRedis()


@pytest.mark.asyncio
async def test_rate_limit_exact_threshold(fake_redis):
    with patch("core.rate_limit.cache") as mock_cache:
        mock_cache.enabled = True
        mock_cache.redis = fake_redis
        
        service = RateLimitService()
        key = "test_key"
        limit = 5
        window = 60
        
        # Requests 1 to 5 should be allowed
        for i in range(1, 6):
            allowed, remaining, retry = await service.is_allowed(key, limit, window)
            assert allowed is True
            assert remaining == limit - i
            assert retry == 0
            
        # Request 6 and 7 should be rejected
        for i in range(2):
            allowed, remaining, retry = await service.is_allowed(key, limit, window)
            assert allowed is False
            assert remaining == 0
            assert retry > 0

@pytest.mark.asyncio
async def test_rate_limit_window_reset(fake_redis):
    with patch("core.rate_limit.cache") as mock_cache:
        mock_cache.enabled = True
        mock_cache.redis = fake_redis
        
        service = RateLimitService()
        key = "test_reset"
        
        # exhaust limit
        for _ in range(5):
            await service.is_allowed(key, 5, 1)
            
        allowed, _, retry = await service.is_allowed(key, 5, 1)
        assert allowed is False
        assert retry == 1  # our math.ceil TTL logic should round up to 1
        
        # Simulate time passing
        fake_redis.ttls[key] = time.time() - 1
        
        allowed, remaining, retry = await service.is_allowed(key, 5, 1)
        assert allowed is True
        assert remaining == 4

@pytest.mark.asyncio
async def test_rate_limit_fail_open():
    with patch("core.rate_limit.cache") as mock_cache:
        mock_cache.enabled = True
        mock_cache.redis = AsyncMock()
        mock_cache.redis.script_load.side_effect = Exception("Redis down")
        
        service = RateLimitService()
        allowed, _, _ = await service.is_allowed("test", 5, 60)
        assert allowed is True # Fails open

@pytest.mark.asyncio
async def test_rate_limit_noscript(fake_redis):
    with patch("core.rate_limit.cache") as mock_cache:
        mock_cache.enabled = True
        mock_cache.redis = fake_redis
        
        service = RateLimitService()
        
        # preload
        await service.is_allowed("test", 5, 60)
        
        # simulate NOSCRIPT cache loss
        fake_redis.scripts.clear()
        
        # Should catch NOSCRIPT, reload, and succeed
        allowed, remaining, _ = await service.is_allowed("test", 5, 60)
        assert allowed is True
        assert remaining == 3
