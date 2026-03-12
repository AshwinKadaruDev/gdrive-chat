import os
import sys
import uuid

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

# Add project root to sys.path so worker.* imports work in tests
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.main import app
from app.dependencies import get_current_user, get_settings
from app.utils.security import SESSION_COOKIE_NAME, create_session


def _make_mock_user():
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "test@example.com"
    user.name = "Test User"
    user.picture_url = None
    user.google_access_token = "encrypted-test-token"
    user.google_refresh_token = "encrypted-test-refresh"
    return user


@pytest.fixture
def mock_user():
    return _make_mock_user()


@pytest.fixture
async def test_client(mock_user):
    """Authenticated test client — auth dependency overridden + valid cookie."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Create a real signed session cookie so the AuthGuardMiddleware passes.
    settings = get_settings()
    session_token = create_session(
        uuid.UUID("00000000-0000-0000-0000-000000000001"), settings
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: session_token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def unauthed_client():
    """Unauthenticated test client — for testing 401 responses."""
    app.dependency_overrides.pop(get_current_user, None)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
