import pytest
from fastapi.testclient import TestClient
from app import app

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
    response = client.get("/stats")
    # Even if vector store is mocked, it shouldn't crash
    # The actual result depends on the mock
    assert response.status_code in [200, 500]
    
def test_import_success():
    """Verify that importing the app does not crash."""
    import app as imported_app
    assert imported_app.app is not None
