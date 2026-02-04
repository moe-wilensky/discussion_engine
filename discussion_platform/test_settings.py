"""
Test settings that inherit from base settings but use SQLite.
"""

from discussion_platform.settings import *

# Override database to use SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {
            "timeout": 20,  # Increase timeout for concurrent operations
        },
        "TEST": {
            "NAME": "file:memorydb_default?mode=memory&cache=shared",
        },
    }
}

# Use in-memory cache for tests (faster and no Redis dependency)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# Use synchronous Celery for tests (no broker needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Twilio test mode
TWILIO_TEST_MODE = True

# Use simple static files storage for tests (no manifest required)
# This avoids needing to run collectstatic before tests
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


# Uncomment to disable migrations (faster but might miss migration issues)
# MIGRATION_MODULES = DisableMigrations()
