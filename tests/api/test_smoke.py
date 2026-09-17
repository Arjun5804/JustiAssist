import pytest
from fastapi.testclient import TestClient
from app import app
from services.auth import get_current_user
from services.database import User

@pytest.fixture
def client(mock_lifespan_dependencies):
    with TestClient(app) as test_client:
        yield test_client

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_stats_endpoint(client):
    app.dependency_overrides[get_current_user] = lambda: User(id=1, email="test@example.com", display_name="Test")
    try:
        response = client.get("/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "statutory" in data
        assert "case_law" in data
        assert "embedding_model" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    
def test_import_success():
    """Verify that importing the app does not crash."""
    import app as imported_app
    assert imported_app.app is not None
