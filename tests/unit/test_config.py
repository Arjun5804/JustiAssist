import os
import pytest
from pydantic import ValidationError
from config import Settings

def test_development_defaults_load_correctly():
    """Test that default settings load correctly in development mode."""
    # Ensure no environment variables interfere
    os.environ.pop("APP_ENV", None)
    os.environ.pop("JWT_SECRET_KEY", None)
    
    settings = Settings(APP_ENV="development")
    
    assert settings.APP_ENV == "development"
    assert settings.JWT_SECRET_KEY.get_secret_value() == "justiassist-secret-change-in-production-2026"
    assert settings.DATABASE_URL == "sqlite:///justiassist.db"
    assert settings.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert settings.DEBUG is False

def test_environment_variables_override_defaults(monkeypatch):
    """Test that environment variables override the default values."""
    monkeypatch.setenv("APP_NAME", "JustiAssist Test")
    monkeypatch.setenv("JWT_EXPIRY_HOURS", "48")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    
    settings = Settings()
    
    assert settings.APP_NAME == "JustiAssist Test"
    assert settings.JWT_EXPIRY_HOURS == 48
    assert settings.GROQ_API_KEY.get_secret_value() == "test_groq_key"

def test_production_rejects_missing_jwt_configuration():
    """Test that production environment rejects weak/default JWT_SECRET_KEY."""
    # Fails if default is used
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", JWT_SECRET_KEY="justiassist-secret-change-in-production-2026")
    assert "secure value in production" in str(exc_info.value)
    
    # Fails if too short
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", JWT_SECRET_KEY="short-secret")
    assert "at least 32 characters" in str(exc_info.value)
    
    # Passes with strong secret
    valid_secret = "a" * 32
    settings = Settings(APP_ENV="production", JWT_SECRET_KEY=valid_secret)
    assert settings.JWT_SECRET_KEY.get_secret_value() == valid_secret

def test_groq_configuration_read_correctly(monkeypatch):
    """Test Groq config is parsed correctly."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkey123")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b")
    
    settings = Settings()
    assert settings.GROQ_API_KEY.get_secret_value() == "gsk_testkey123"
    assert settings.GROQ_MODEL == "llama-3.1-8b"

def test_ollama_is_not_required():
    """Test that Ollama is optional and doesn't fail validation if omitted/defaults used."""
    settings = Settings()
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"
    assert settings.OLLAMA_MODEL in ("llama3.2", "llama3.1:8b")

def test_cors_configuration_parses_correctly():
    """Test CORS configuration."""
    settings = Settings(ALLOWED_ORIGINS="http://example.com,http://test.com")
    assert settings.ALLOWED_ORIGINS == "http://example.com,http://test.com"
    assert len(settings.ALLOWED_ORIGINS.split(",")) == 2

def test_secrets_not_exposed_in_repr():
    """Check that pydantic-settings doesn't expose secrets insecurely, although Pydantic
    requires SecretStr for full hiding, we just ensure our error messages don't print it.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", JWT_SECRET_KEY="insecure_password_123")
    
    error_msg = exc_info.value.errors()[0]["msg"]
    assert "insecure_password_123" not in error_msg
    assert "at least 32 characters" in error_msg
