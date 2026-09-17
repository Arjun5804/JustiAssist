import pytest
from pydantic import ValidationError
import os
import importlib
from unittest import mock
import config

def test_production_rejects_sqlite():
    """Test that SQLite is explicitly blocked in production."""
    with mock.patch.dict(os.environ, {"APP_ENV": "production", "DATABASE_URL": "sqlite:///test.db", "JWT_SECRET_KEY": "a_very_secure_and_long_jwt_secret_key_12345"}):
        with pytest.raises(ValidationError) as excinfo:
            config.Settings()
        assert "PostgreSQL is required in production" in str(excinfo.value)

def test_production_requires_valid_jwt():
    """Test that default or weak JWT secrets are rejected in production."""
    with mock.patch.dict(os.environ, {"APP_ENV": "production", "DATABASE_URL": "postgresql://user:pass@localhost/db", "JWT_SECRET_KEY": "too-short"}):
        with pytest.raises(ValidationError) as excinfo:
            config.Settings()
        assert "JWT_SECRET_KEY must be at least 32 characters long" in str(excinfo.value)
        
    with mock.patch.dict(os.environ, {"APP_ENV": "production", "DATABASE_URL": "postgresql://user:pass@localhost/db", "JWT_SECRET_KEY": "justiassist-secret-change-in-production-2026"}):
        with pytest.raises(ValidationError) as excinfo:
            config.Settings()
        assert "JWT_SECRET_KEY must be set to a secure value in production" in str(excinfo.value)

def test_development_allows_sqlite():
    """Test that SQLite is allowed in development/testing."""
    with mock.patch.dict(os.environ, {"APP_ENV": "development", "DATABASE_URL": "sqlite:///test.db"}):
        settings = config.Settings()
        assert settings.APP_ENV == "development"
        assert settings.DATABASE_URL.startswith("sqlite")
        
    with mock.patch.dict(os.environ, {"APP_ENV": "testing", "DATABASE_URL": "sqlite:///test_ci.db"}):
        settings = config.Settings()
        assert settings.APP_ENV == "testing"
        assert settings.DATABASE_URL.startswith("sqlite")
