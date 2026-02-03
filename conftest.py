"""Root conftest for pytest database configuration."""

import pytest
import os
import django
from django.conf import settings


# Override settings before Django is configured
def pytest_configure(config):
    """Configure test database to use SQLite."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'discussion_platform.settings')
    
    # Import settings module
    from django.conf import settings
    
    # Override database settings for testing
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
