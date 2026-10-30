import pytest
from heladeria_backend.config.settings import MongoSettings

def test_mongo_settings_pool_validation():
    with pytest.raises(ValueError):
        MongoSettings(
            url="mongodb://localhost:27017",
            database="test",
            pool_min_size=100,
            pool_max_size=10,
            server_selection_timeout_ms=5000,
            connect_timeout_ms=5000,
            socket_timeout_ms=30000,
        )

def test_mongo_settings_invalid_uri():
    with pytest.raises(ValueError):
        MongoSettings(
            url="http://localhost:27017",
            database="test",
            pool_min_size=5,
            pool_max_size=50,
            server_selection_timeout_ms=5000,
            connect_timeout_ms=5000,
            socket_timeout_ms=30000,
        )


def test_mongo_settings_valid():
    config = MongoSettings(
        url="mongodb://localhost:27017",
        database="test",
        pool_min_size=5,
        pool_max_size=50,
        server_selection_timeout_ms=5000,
        connect_timeout_ms=5000,
        socket_timeout_ms=30000,
    )
    assert config.pool_min_size == 5
    assert config.pool_max_size == 50

def test_app_settings_loaded(settings):
    assert settings.app.slug
    assert settings.app.environment in ("development", "staging", "production", "testing")