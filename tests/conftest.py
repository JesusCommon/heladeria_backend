import pytest
from heladeria_backend.config.settings import get_settings

@pytest.fixture
def settings():
    return get_settings()