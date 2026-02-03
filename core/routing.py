"""
WebSocket URL routing for Channels.

Maps WebSocket URLs to consumers.
"""

from django.urls import re_path
from core.consumers import DiscussionConsumer

websocket_urlpatterns = [
    re_path(r'ws/discussions/(?P<discussion_id>\d+)/$', DiscussionConsumer.as_asgi()),
]
