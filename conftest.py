"""Root conftest for pytest database configuration."""

import pytest
import os
import django
from django.conf import settings


# Override settings before Django is configured
def pytest_configure(config):
    """Configure test database to use SQLite."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "discussion_platform.settings")

    # Import settings module
    from django.conf import settings

    # Override database settings for testing
    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            # Enable async support
            "ATOMIC_REQUESTS": False,
            "CONN_MAX_AGE": 0,
            # Important: Allow sharing database across threads for live_server
            "OPTIONS": {
                "check_same_thread": False,
            },
        }
    }


# Enable pytest-asyncio auto mode for all async fixtures and tests
@pytest.fixture(scope="session")
def event_loop_policy():
    """Set the event loop policy for async tests."""
    import asyncio
    return asyncio.get_event_loop_policy()


# Django async database support
@pytest.fixture(scope="session", autouse=True)
def setup_async_db():
    """Ensure Django is configured for async database operations."""
    import django
    from django.conf import settings
    
    if not settings.configured:
        django.setup()
    
    # Enable async-unsafe operations in tests
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
