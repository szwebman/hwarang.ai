"""Test fixtures for hwarang-api."""

import pytest
from fastapi.testclient import TestClient

from hwarang_api.config import Settings
from hwarang_api.main import create_app


@pytest.fixture
def settings():
    """Test settings with auth disabled."""
    return Settings(
        require_auth=False,
        model_path="./test_models",
        default_model="test-model",
        database_url="sqlite+aiosqlite:///test.db",
    )


@pytest.fixture
def app(settings):
    """Test FastAPI app."""
    return create_app(settings)


@pytest.fixture
def client(app):
    """Test client."""
    return TestClient(app)
