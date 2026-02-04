"""
Discussion Platform initialization.

Loads Celery app for async task processing.
"""

# This will ensure the Celery app is always imported when Django starts
from .celery import app as celery_app

__all__ = ("celery_app",)
