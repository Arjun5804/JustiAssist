import pytest
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from services.cache import CacheService

pytestmark = pytest.mark.asyncio

@pytest.fixture
def disabled_config():
    with patch("services.cache.settings") as mock_settings:
        mock_settings.REDIS_ENABLED = False
        yield mock_settings

@pytest.fixture
def enabled_config():
    with patch("services.cache.settings") as mock_settings:
        mock_settings.REDIS_ENABLED = True
        mock_settings.REDIS_DEFAULT_TTL = 3600
        mock_settings.REDIS_URL = "redis://mock"
        yield mock_settings

async def test_redis_disabled(disabled_config):
    cache = CacheService()
    await cache.init()
    assert cache.redis is None

    # Should act as no-op and return None
    await cache.set("key", {"data": 1})
    val = await cache.get("key")
    assert val is None

@patch("redis.asyncio.from_url")
async def test_cache_hit(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.get.return_value = '{"foo": "bar"}'

    cache = CacheService()
    await cache.init()

    val = await cache.get("justiassist:v1:test:key")
    assert val == {"foo": "bar"}
    mock_redis.get.assert_called_once_with("justiassist:v1:test:key")

@patch("redis.asyncio.from_url")
async def test_cache_miss(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.get.return_value = None

    cache = CacheService()
    await cache.init()

    val = await cache.get("justiassist:v1:test:key")
    assert val is None

@patch("redis.asyncio.from_url")
async def test_cache_population(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis

    cache = CacheService()
    await cache.init()

    await cache.set("justiassist:v1:test:key", {"user": 1}, ttl=500)
    mock_redis.setex.assert_called_once_with("justiassist:v1:test:key", 500, '{"user": 1}')

@patch("redis.asyncio.from_url")
async def test_malformed_json(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.get.return_value = "{malformed: true"

    cache = CacheService()
    await cache.init()

    # Should degrade gracefully to cache miss
    val = await cache.get("key")
    assert val is None

@patch("redis.asyncio.from_url")
async def test_get_failure(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.get.side_effect = Exception("Connection Refused")

    cache = CacheService()
    await cache.init()

    val = await cache.get("key")
    assert val is None

@patch("redis.asyncio.from_url")
async def test_set_failure(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.setex.side_effect = Exception("Connection Refused")

    cache = CacheService()
    await cache.init()

    # Should not raise exception
    await cache.set("key", {"data": 1})

@patch("redis.asyncio.from_url")
async def test_delete_failure(mock_from_url, enabled_config):
    mock_redis = AsyncMock()
    mock_from_url.return_value = mock_redis
    mock_redis.delete.side_effect = Exception("Connection Refused")

    cache = CacheService()
    await cache.init()

    # Should not raise exception
    await cache.delete("key")

@patch("services.chat_memory.cache")
@patch("services.chat_memory.get_db_session")
async def test_chat_history_fallback(mock_get_db, mock_cache):
    # Setup mock cache miss
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    # Mock DB
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    mock_query = mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value
    mock_query.all.return_value = []
    
    from services.chat_memory import get_history
    res = await get_history(1, "conv1")
    assert res == []
    
    mock_cache.get.assert_called_once_with("justiassist:v1:chat:history:1:conv1")
    mock_cache.set.assert_called_once_with("justiassist:v1:chat:history:1:conv1", [], ttl=3600)

@patch("services.chat_memory.cache")
@patch("services.chat_memory.get_db_session")
async def test_recent_conversations_fallback(mock_get_db, mock_cache):
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    mock_query = mock_db.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value
    mock_query.all.return_value = []
    
    from services.chat_memory import get_recent_conversations
    res = await get_recent_conversations(1)
    assert res == []
    
    mock_cache.get.assert_called_once_with("justiassist:v1:chat:conversations:1")
    mock_cache.set.assert_called_once_with("justiassist:v1:chat:conversations:1", [], ttl=900)

@patch("api.documents.cache")
@patch("api.documents.get_db_session")
@patch("api.documents.session_manager")
async def test_document_list_fallback(mock_session_manager, mock_get_db, mock_cache):
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    mock_db.query.return_value.filter.return_value.all.return_value = []
    
    from api.documents import list_session_documents
    from services.database import User
    
    user = User(id=1)
    res = await list_session_documents("session1", current_user=user)
    
    assert res["session_id"] == "session1"
    assert res["documents"] == []
    
    mock_cache.get.assert_called_once_with("justiassist:v1:docs:session:1:session1")
    mock_cache.set.assert_called_once_with("justiassist:v1:docs:session:1:session1", res, ttl=1800)

@patch("services.chat_memory.cache.redis")
@patch("services.chat_memory.get_db_session")
async def test_db_write_succeeds_despite_invalidation_failure(mock_get_db, mock_redis):
    # Ensure cache is considered enabled and initialized
    from services.chat_memory import cache
    cache.enabled = True
    cache.redis = mock_redis
    mock_redis.delete = AsyncMock(side_effect=Exception("Redis down!"))
    
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    # Mock clear history to simulate deletion
    mock_filter1 = mock_db.query.return_value.filter.return_value
    mock_filter2 = mock_filter1.filter.return_value
    mock_filter2.count.return_value = 1
    
    from services.chat_memory import clear_history
    count = await clear_history(user_id=1, conversation_id="conv1")
    
    assert count == 1
    mock_db.commit.assert_called_once()
    mock_redis.delete.assert_called() # despite exception, execution continued to return count
