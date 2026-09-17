import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app import app
from services.auth import create_access_token, get_current_user
from api.admin import get_admin_user
from services.database import User

client = TestClient(app)



# A. Admin Authentication
def test_admin_endpoints_protected():
    assert client.post("/build-indices").status_code == 401
    assert client.get("/stats").status_code == 401
    assert client.get("/api/news").status_code == 401

@patch("api.admin.deps.vector_store")
def test_admin_endpoints_authenticated(mock_vs):
    # Should bypass 401 and 403
    app.dependency_overrides[get_admin_user] = lambda: User(id=1, email="admin@example.com", display_name="Admin")
    mock_vs.get_statistics.return_value = {"stats": "ok"}
    try:
        res = client.get("/stats")
        assert res.status_code == 200
    finally:
        app.dependency_overrides.pop(get_admin_user, None)

# B. Input Bounds
def test_input_bounds_text():
    # Valid
    payload = {
        "case_type": "criminal",
        "case_facts": "A" * 20,
    }
    res = client.post("/api/predict/case", json=payload)
    assert res.status_code != 422

    # Oversized text
    payload["case_facts"] = "A" * 5001
    res = client.post("/api/predict/case", json=payload)
    assert res.status_code == 422

def test_input_bounds_list():
    # Valid
    payload = {
        "query": "test query",
        "offense_sections": ["S1"] * 10
    }
    res = client.post("/api/v2/query", json=payload)
    assert res.status_code != 422

    # Oversized list
    payload["offense_sections"] = ["S1"] * 11
    res = client.post("/api/v2/query", json=payload)
    assert res.status_code == 422

# C. Login Timing Mitigation
@patch("services.auth.verify_password")
@patch("services.auth.get_db_session")
def test_login_timing_mitigation(mock_get_db, mock_verify):
    mock_db = mock_get_db.return_value
    # Simulate nonexistent user
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_verify.return_value = False
    
    res = client.post("/api/auth/login", json={"email": "nonexistent@example.com", "password": "password"})
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]
    
    # Assert dummy path executed
    assert mock_verify.call_count == 1
    args, kwargs = mock_verify.call_args
    assert args[0] == "password"
    assert args[1] == "$2b$12$R73MvdJqXhZk21t/RTcyqeB4EJE52W4Dg.HMNKWlfO5YjFggn3K2S"

# D. Rate Limiting
@patch("core.rate_limit.rate_limit_service.is_allowed")
def test_rate_limiting_success(mock_is_allowed):
    mock_is_allowed.return_value = (True, 5, 0)
    
    payload = {
        "email": "newuser@example.com", 
        "password": "password",
        "display_name": "Test User"
    }
    # Doesn't matter if it fails downstream (e.g. 500 database), it shouldn't 429
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code != 429

@patch("core.rate_limit.rate_limit_service.is_allowed")
def test_rate_limiting_rejection(mock_is_allowed):
    mock_is_allowed.return_value = (False, 0, 45) # 45 seconds retry-after
    
    payload = {
        "email": "newuser2@example.com", 
        "password": "password",
        "display_name": "Test User 2"
    }
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code == 429
    assert "Too Many Requests" in res.json()["detail"]

# E. SSE Regression
def test_sse_missing_ticket():
    res = client.get("/api/query/stream?query=test")
    assert res.status_code == 401
    assert "Missing SSE ticket" in res.json()["detail"]

def test_sse_invalid_ticket():
    res = client.get("/api/query/stream?query=test&ticket=invalid.jwt.token")
    assert res.status_code == 401
    assert "Invalid or expired SSE ticket" in res.json()["detail"]
