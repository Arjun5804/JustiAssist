import os
import pytest
from pydantic import ValidationError, SecretStr
from config import Settings

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure tests run in a clean environment without .env interference."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("INDIAN_KANOON_API_KEY", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("JWT_EXPIRY_HOURS", raising=False)

def test_valid_development_env():
    """1. Test valid development."""
    settings = Settings(_env_file=None, APP_ENV="development")
    assert settings.APP_ENV == "development"

def test_valid_production_env():
    """2. Test valid production (requires valid secret)."""
    settings = Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="a" * 32, DATABASE_URL="postgresql://user:pass@localhost/db")
    assert settings.APP_ENV == "production"

def test_valid_testing_env():
    """3. Test valid testing."""
    settings = Settings(_env_file=None, APP_ENV="testing")
    assert settings.APP_ENV == "testing"

def test_invalid_app_env_rejected():
    """4. Test invalid APP_ENV rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, APP_ENV="banana")
    assert "Input should be 'development', 'production' or 'testing'" in str(exc_info.value)

def test_optional_api_keys_can_be_absent():
    """5, 6, 7. Test optional keys can be absent."""
    settings = Settings(_env_file=None)
    assert settings.GROQ_API_KEY is None
    assert settings.FIRECRAWL_API_KEY is None
    assert settings.INDIAN_KANOON_API_KEY is None

def test_configured_secrets_remain_secretstr():
    """8. Test configured secrets remain SecretStr."""
    settings = Settings(
        _env_file=None,
        GROQ_API_KEY="groq_test",
        FIRECRAWL_API_KEY="fc_test",
        INDIAN_KANOON_API_KEY="ik_test"
    )
    assert isinstance(settings.GROQ_API_KEY, SecretStr)
    assert settings.GROQ_API_KEY.get_secret_value() == "groq_test"
    
    assert isinstance(settings.FIRECRAWL_API_KEY, SecretStr)
    assert settings.FIRECRAWL_API_KEY.get_secret_value() == "fc_test"

    assert isinstance(settings.INDIAN_KANOON_API_KEY, SecretStr)
    assert settings.INDIAN_KANOON_API_KEY.get_secret_value() == "ik_test"

def test_production_rejects_missing_default_weak_jwt_secret():
    """9. Test production rejects missing/default/weak JWT secret."""
    # Fails if default is used
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="justiassist-secret-change-in-production-2026")
    assert "secure value in production" in str(exc_info.value)
    
    # Fails if missing (None or empty string)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="")
    assert "secure value in production" in str(exc_info.value)

    # Fails if too short
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="short-secret")
    assert "at least 32 characters" in str(exc_info.value)

def test_production_accepts_strong_secret():
    """10. Test production accepts a >=32-character secret."""
    valid_secret = "a" * 32
    settings = Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY=valid_secret, DATABASE_URL="postgresql://user:pass@localhost/db")
    assert settings.JWT_SECRET_KEY.get_secret_value() == valid_secret

def test_cors_parsing_still_works():
    """11. Test CORS parsing still works."""
    settings = Settings(_env_file=None, ALLOWED_ORIGINS="http://example.com,http://test.com")
    assert settings.ALLOWED_ORIGINS == "http://example.com,http://test.com"
    assert len(settings.ALLOWED_ORIGINS.split(",")) == 2

def test_environment_variables_still_override_defaults(monkeypatch):
    """12. Test environment variables still override defaults."""
    monkeypatch.setenv("APP_NAME", "JustiAssist Test")
    monkeypatch.setenv("JWT_EXPIRY_HOURS", "48")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    
    settings = Settings(_env_file=None)
    
    assert settings.APP_NAME == "JustiAssist Test"
    assert settings.JWT_EXPIRY_HOURS == 48
    assert settings.GROQ_API_KEY.get_secret_value() == "test_groq_key"

def test_ollama_configuration_remains_optional():
    """13. Test Ollama configuration remains optional."""
    settings = Settings()
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"
    assert settings.OLLAMA_MODEL in ("llama3.2", "llama3.1:8b")

def test_secrets_not_exposed_in_repr():
    """Check that pydantic-settings doesn't expose secrets insecurely."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="insecure_password_123")
    
    error_msg = exc_info.value.errors()[0]["msg"]
    assert "insecure_password_123" not in error_msg
    assert "at least 32 characters" in error_msg
