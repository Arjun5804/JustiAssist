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


@patch("services.chat_memory.cache")
@patch("services.chat_memory.get_db_session")
async def test_canonical_page_satisfies_smaller_limit(mock_get_db, mock_cache):
    # Simulate a cached canonical page with 20 items
    # They should be in chronological order (oldest first)
    canonical_cache = [{"id": i, "content": f"msg {i}"} for i in range(1, 21)]
    mock_cache.get = AsyncMock(return_value=canonical_cache)
    
    # Do NOT expect the db to be queried!
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    from services.chat_memory import get_history
    
    # 1. Query with limit=6, offset=0
    res = await get_history(user_id=1, conversation_id="conv1", limit=6, offset=0)
    
    # Assertions
    # 1. Redis is checked for the canonical page
    mock_cache.get.assert_called_once_with("justiassist:v1:chat:history:1:conv1")
    
    # 2. Cache hit avoids DB query
    mock_db.query.assert_not_called()
    
    # 3. Returned result respects limit=6
    assert len(res) == 6
    
    # 4. Chronological ordering remains correct (last 6 items of the 20)
    # The last 6 items should be IDs 15, 16, 17, 18, 19, 20
    expected_ids = [15, 16, 17, 18, 19, 20]
    actual_ids = [m["id"] for m in res]
    assert actual_ids == expected_ids

@patch("services.chat_memory.cache")
@patch("services.chat_memory.get_db_session")
async def test_cache_miss_populates_canonical_page(mock_get_db, mock_cache):
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    # Simulate DB returning 8 items (fewer than 20) in descending order
    # Descending means newest first!
    class MockMsg:
        def __init__(self, id_val):
            self.id = id_val
        def to_dict(self):
            return {"id": self.id}
    
    # IDs 8 to 1 (newest to oldest)
    db_items = [MockMsg(i) for i in range(8, 0, -1)]
    mock_query = mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value
    mock_query.all.return_value = db_items
    
    from services.chat_memory import get_history
    
    # We query with limit=6
    res = await get_history(user_id=1, conversation_id="conv1", limit=6, offset=0)
    
    # 1. DB should have been queried with limit=20 (fetch_limit)
    mock_query_limit = mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.offset.return_value.limit
    mock_query_limit.assert_called_with(20)
    
    # 2. Cache should be populated with the full 8 items (in chronological order, reversed from DB)
    expected_full_cache = [{"id": i} for i in range(1, 9)]
    mock_cache.set.assert_called_once_with("justiassist:v1:chat:history:1:conv1", expected_full_cache, ttl=3600)
    
    # 3. Returned result should only be the last 6 items of those 8 (chronological)
    # IDs should be 3, 4, 5, 6, 7, 8
    expected_result = [{"id": i} for i in range(3, 9)]
    assert res == expected_result
