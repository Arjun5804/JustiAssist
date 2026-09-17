import pytest
from pydantic import ValidationError
from config import Settings
from fastapi.testclient import TestClient
from app import app
from services.auth import create_access_token, create_sse_ticket, JWT_SECRET_KEY, JWT_ALGORITHM
from jose import jwt
from datetime import datetime, timedelta
import uuid

# --- Configuration Tests ---

def test_production_sqlite_rejected():
    with pytest.raises(ValidationError, match="PostgreSQL is required in production"):
        Settings(APP_ENV="production", DATABASE_URL="sqlite:///test.db", JWT_SECRET_KEY="super_secret_key_long_enough_for_prod_123456789")

def test_production_sqlite_aiosqlite_rejected():
    with pytest.raises(ValidationError, match="PostgreSQL is required in production"):
        Settings(APP_ENV="production", DATABASE_URL="sqlite+aiosqlite:///test.db", JWT_SECRET_KEY="super_secret_key_long_enough_for_prod_123456789")

def test_production_weak_secret_rejected():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be at least 32 characters long"):
        Settings(APP_ENV="production", DATABASE_URL="postgresql://user:pass@localhost/db", JWT_SECRET_KEY="weak_secret")

def test_production_default_secret_rejected():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be set to a secure value"):
        Settings(APP_ENV="production", DATABASE_URL="postgresql://user:pass@localhost/db", JWT_SECRET_KEY="justiassist-secret-change-in-production-2026")

def test_valid_production_configuration_accepted():
    s = Settings(APP_ENV="production", DATABASE_URL="postgresql://user:pass@localhost/db", JWT_SECRET_KEY="super_secret_key_long_enough_for_prod_123456789")
    assert s.APP_ENV == "production"

def test_development_sqlite_accepted():
    s = Settings(APP_ENV="development", DATABASE_URL="sqlite:///test.db")
    assert s.APP_ENV == "development"

def test_testing_sqlite_accepted():
    s = Settings(APP_ENV="testing", DATABASE_URL="sqlite:///test.db")
    assert s.APP_ENV == "testing"


# --- SSE Ticket Tests ---

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def test_user():
    # Helper to setup a test user. Assumes a test db is active.
    from services.database import get_db_session, User
    from services.auth import hash_password
    db = get_db_session()
    email = f"test_{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        display_name="Test User",
        hashed_password=hash_password("password"),
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id

def test_sse_missing_ticket(test_user):
    response = client.get("/api/query/stream?query=hello")
    assert response.status_code == 401
    assert "Missing SSE ticket" in response.text

def test_sse_invalid_ticket():
    response = client.get("/api/query/stream?query=hello&ticket=invalid.jwt.token")
    assert response.status_code == 401
    assert "Invalid or expired SSE ticket" in response.text

def test_sse_expired_ticket(test_user):
    expire = datetime.utcnow() - timedelta(seconds=30)
    payload = {
        "sub": str(test_user),
        "type": "sse",
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow() - timedelta(seconds=60),
    }
    ticket = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 401

def test_ordinary_access_jwt_used_as_ticket_rejected(test_user):
    token = create_access_token(test_user, "test@example.com")
    response = client.get(f"/api/query/stream?query=hello&ticket={token}")
    assert response.status_code == 401

def test_wrong_ticket_type_rejected(test_user):
    expire = datetime.utcnow() + timedelta(seconds=30)
    payload = {
        "sub": str(test_user),
        "type": "not_sse",
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
    }
    ticket = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 401

def test_old_token_param_rejected(test_user):
    # Pass access JWT as 'token' which was the old way
    token = create_access_token(test_user, "test@example.com")
    response = client.get(f"/api/query/stream?query=hello&token={token}")
    # Now it hits "Missing SSE ticket" because ticket is not provided
    assert response.status_code == 401

def test_missing_sub_in_ticket_rejected():
    expire = datetime.utcnow() + timedelta(seconds=30)
    payload = {
        "type": "sse",
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
    }
    ticket = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 401

def test_malformed_sub_in_ticket_rejected():
    expire = datetime.utcnow() + timedelta(seconds=30)
    payload = {
        "sub": "not-an-integer",
        "type": "sse",
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
    }
    ticket = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 401

def test_nonexistent_user_in_ticket_rejected():
    expire = datetime.utcnow() + timedelta(seconds=30)
    payload = {
        "sub": "999999",
        "type": "sse",
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
    }
    ticket = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 401

def test_valid_sse_ticket_accepted(test_user):
    ticket = create_sse_ticket(test_user)
    response = client.get(f"/api/query/stream?query=hello&ticket={ticket}")
    assert response.status_code == 200
    # Stream returns valid data

# --- Authorization Tests ---

def test_sse_ticket_user_a_cannot_access_user_b_conversation(test_user):
    user_a = test_user
    # Need a second user
    from services.database import get_db_session, User
    from services.auth import hash_password
    db = get_db_session()
    user = User(
        email=f"user_b_{uuid.uuid4()}@example.com",
        display_name="User B",
        hashed_password=hash_password("password"),
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_b = user.id
    
    # Create conversation for User A
    conv_id = str(uuid.uuid4())[:12]
    from services.chat_memory import save_message
    import asyncio
    asyncio.run(save_message(user_a, "user", "Hello A", conv_id))
    db.close()
    
    # User B tries to access User A's conversation
    ticket_b = create_sse_ticket(user_b)
    response = client.get(f"/api/query/stream?query=test&ticket={ticket_b}&conversation_id={conv_id}")
    assert response.status_code == 200
    content = response.content.decode('utf-8')
    assert "error" in content
    assert "belongs to another user" in content or "An internal error occurred" in content

# --- Exception Handling Tests ---

def test_internal_exception_returns_generic_response():
    # Let's hit an endpoint that doesn't exist or we can mock one to raise Exception
    @app.get("/api/test_error_500")
    async def test_error_500():
        raise Exception("Secret internal database error message 12345")
        
    response = client.get("/api/test_error_500")
    assert response.status_code == 500
    assert response.json() == {"detail": "An internal error occurred while processing your request."}
    assert "Secret internal database error" not in response.text
