import pytest
from unittest.mock import patch
import importlib

def test_engine_config_sqlite():
    """Verify that sqlite URLs receive check_same_thread=False"""
    with patch("config.settings.DATABASE_URL", "sqlite:///test.db"):
        # We need to reload the module to trigger the engine creation with the patched URL
        import services.database
        importlib.reload(services.database)
        
        # Verify dialect is sqlite
        assert services.database.engine.url.get_backend_name() == "sqlite"
        
        # Verify check_same_thread is in the dialet connect args
        assert services.database.connect_args.get("check_same_thread") is False

def test_engine_config_postgres():
    """Verify that postgres URLs do NOT receive check_same_thread=False"""
    with patch("config.settings.DATABASE_URL", "postgresql://user:pass@localhost/db"):
        import services.database
        importlib.reload(services.database)
        
        # Verify dialect is postgresql
        assert services.database.engine.url.get_backend_name() == "postgresql"
        
        # Verify check_same_thread is NOT passed to postgres
        assert "check_same_thread" not in services.database.connect_args
