import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app import app
from core.logger import correlation_id_var
from audit_logger import audit_logger, RetrievalEvent
from metrics import metrics
from config import settings
from services.auth import get_current_user

client = TestClient(app)

def test_request_correlation_middleware():
    """Test that Request ID middleware sets and returns X-Request-ID, and handles invalid ones."""
    # Normal request
    response = client.get("/health/liveness")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    req_id = response.headers["X-Request-ID"]
    assert len(req_id) > 10

    # Provided valid request ID
    custom_id = "test-custom-1234"
    response2 = client.get("/health/liveness", headers={"X-Request-ID": custom_id})
    assert response2.headers["X-Request-ID"] == custom_id

    # Provided invalid/dangerous request ID (too long or invalid chars)
    dangerous_id = "invalid_id_with_symbols@!"
    response3 = client.get("/health/liveness", headers={"X-Request-ID": dangerous_id})
    assert response3.headers["X-Request-ID"] != dangerous_id
    
    # Ensure ContextVar is reset (we can only observe this indirectly in test, or check outside request context)
    assert correlation_id_var.get() == ""


def test_audit_logger_pii_removal():
    """Test that raw query texts are not serialized in audit logs."""
    query = "sensitive case fact about victim John Doe"
    reformulated = "John Doe case laws"
    
    with patch.object(audit_logger, '_log') as mock_log:
        audit_logger.log_retrieval("q1", query, reformulated, [], 0.9, "high")
        
        mock_log.assert_called_once()
        event = mock_log.call_args[0][0]
        
        assert isinstance(event, RetrievalEvent)
        assert not hasattr(event, 'query_text')
        assert not hasattr(event, 'reformulated_query')
        assert hasattr(event, 'query_hash')
        assert hasattr(event, 'reformulated_query_hash')
        
        # Verify it's a hash, not raw text
        assert query not in event.query_hash
        assert reformulated not in event.reformulated_query_hash
        assert len(event.query_hash) == 64  # SHA-256


@patch('services.database.engine.connect')
@patch('api.admin.deps')
def test_health_endpoints(mock_deps, mock_db_connect):
    """Test health liveness and readiness logic."""
    # Liveness is cheap
    liveness_res = client.get("/health/liveness")
    assert liveness_res.status_code == 200
    assert liveness_res.json() == {"status": "alive"}

    # Readiness dependencies mocked
    mock_db_connect.return_value.__enter__.return_value.execute.return_value = True
    mock_deps.vector_store.statutory_index = object()
    
    # 1. Everything ready
    ready_res = client.get("/health/readiness")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"
    
    # 2. VectorStore missing
    mock_deps.vector_store.statutory_index = None
    not_ready_res1 = client.get("/health/readiness")
    assert not_ready_res1.status_code == 503
    assert not_ready_res1.json()["status"] == "not_ready"
    assert not_ready_res1.json()["vector_store"] == "not_ready"
    
    # 3. Database missing
    mock_deps.vector_store.statutory_index = object()
    mock_db_connect.side_effect = Exception("DB Connection Refused")
    not_ready_res2 = client.get("/health/readiness")
    assert not_ready_res2.status_code == 503
    assert not_ready_res2.json()["database"] == "not_ready"
    
    # Exception strings should not be leaked
    assert "Connection Refused" not in str(not_ready_res2.json())


def test_admin_authorization():
    """Test that admin endpoints are secured and fail closed."""
    # Reset config for test
    original_emails = settings.ADMIN_EMAILS
    
    # Mock user dependency
    async def mock_get_current_user_no_admin():
        user = MagicMock()
        user.email = "admin@justiassist.com"
        return user
        
    app.dependency_overrides[get_current_user] = mock_get_current_user_no_admin
    
    # 1. No admin configured (fail closed)
    settings.ADMIN_EMAILS = ""
    res_no_admin = client.get("/metrics")
    assert res_no_admin.status_code == 403
    
    # 2. Configured admin
    settings.ADMIN_EMAILS = "admin@justiassist.com, another@test.com"
    res_admin = client.get("/metrics")
    assert res_admin.status_code == 200
    
    # 3. Authenticated but non-admin
    async def mock_get_current_user_non_admin():
        user = MagicMock()
        user.email = "user@justiassist.com"
        return user
        
    app.dependency_overrides[get_current_user] = mock_get_current_user_non_admin
    res_non_admin = client.get("/metrics")
    assert res_non_admin.status_code == 403
    
    # Clean up
    settings.ADMIN_EMAILS = original_emails
    app.dependency_overrides = {}


def test_metrics_aggregation():
    """Test gauge increment/decrement and basic tracking."""
    metrics.reset()
    
    # SSE gauge tracking
    metrics.incr("sse_active_connections")
    metrics.incr("sse_active_connections")
    metrics.decr("sse_active_connections")
    
    snapshot = metrics.get_metrics()
    assert snapshot["sse_active_connections"] == 1
    
    # RAG tracking
    metrics.incr("statutory_results_total", 5)
    snapshot2 = metrics.get_metrics()
    assert snapshot2["statutory_results_total"] == 5

