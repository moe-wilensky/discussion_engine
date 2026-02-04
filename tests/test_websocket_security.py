"""
Tests for WebSocket security and authorization.

Tests that WebSocket connections properly enforce authentication
and participant authorization checks.
"""

import pytest
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from core.consumers import DiscussionConsumer
from core.models import Discussion, DiscussionParticipant, PlatformConfig
from core.services.discussion_service import DiscussionService

User = get_user_model()


@pytest.fixture
async def websocket_test_data(db):
    """Set up test data for WebSocket tests."""
    # Create platform config
    await database_sync_to_async(PlatformConfig.objects.get_or_create)(
        pk=1,
        defaults={
            "max_discussion_participants": 10,
            "responses_to_unlock_invites": 5,
        },
    )

    # Create test users
    user1 = await database_sync_to_async(User.objects.create_user)(
        username="participant1", phone_number="+11234567890"
    )
    user2 = await database_sync_to_async(User.objects.create_user)(
        username="participant2", phone_number="+11234567891"
    )
    user3 = await database_sync_to_async(User.objects.create_user)(
        username="outsider", phone_number="+11234567892"
    )

    # Create a discussion with user1 as initiator
    def _create_discussion():
        discussion = DiscussionService.create_discussion(
            initiator=user1,
            headline="Test Discussion",
            details="Test details",
            mrm=30,
            rtm=2.0,
            mrl=2000,
            initial_invites=[user2],
        )
        return discussion

    discussion = await database_sync_to_async(_create_discussion)()

    return {
        "user1": user1,
        "user2": user2,
        "user3": user3,
        "discussion": discussion,
    }


@pytest.mark.asyncio
class TestWebSocketSecurity:
    """Test WebSocket security and authorization."""

    async def test_unauthenticated_user_cannot_connect(self, websocket_test_data):
        """Test that unauthenticated users cannot connect to WebSocket."""
        discussion = websocket_test_data["discussion"]

        # Create communicator without user in scope (unauthenticated)
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = None

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be rejected
        assert not connected

        await communicator.disconnect()

    async def test_authenticated_user_not_participant_cannot_connect(
        self, websocket_test_data
    ):
        """Test that authenticated users who are not participants cannot connect."""
        discussion = websocket_test_data["discussion"]
        user3 = websocket_test_data["user3"]

        # Create communicator with user3 (not a participant)
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user3

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be rejected
        assert not connected

        await communicator.disconnect()

    async def test_participant_can_connect(self, websocket_test_data):
        """Test that participants can successfully connect to WebSocket."""
        discussion = websocket_test_data["discussion"]
        user1 = websocket_test_data["user1"]

        # Create communicator with user1 (initiator/participant)
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be accepted
        assert connected

        await communicator.disconnect()

    async def test_invited_participant_can_connect(self, websocket_test_data):
        """Test that invited participants can connect to WebSocket."""
        discussion = websocket_test_data["discussion"]
        user2 = websocket_test_data["user2"]

        # Create communicator with user2 (invited participant)
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user2

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be accepted
        assert connected

        await communicator.disconnect()

    async def test_observer_can_connect(self, websocket_test_data):
        """Test that observers can connect to WebSocket (they are still participants)."""
        discussion = websocket_test_data["discussion"]
        user2 = websocket_test_data["user2"]

        # Make user2 an observer
        def _make_observer():
            participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=user2
            )
            participant.role = "temporary_observer"
            participant.observer_reason = "mrp_expired"
            participant.save()

        await database_sync_to_async(_make_observer)()

        # Create communicator with user2 (now observer)
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user2

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be accepted (observers are still participants)
        assert connected

        await communicator.disconnect()

    async def test_nonexistent_discussion_rejects_connection(self, websocket_test_data):
        """Test that connection to non-existent discussion is rejected."""
        user1 = websocket_test_data["user1"]
        fake_discussion_id = "00000000-0000-0000-0000-000000000000"

        # Create communicator with valid user but fake discussion
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{fake_discussion_id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": fake_discussion_id}
        }
        communicator.scope["user"] = user1

        # Attempt to connect
        connected, subprotocol = await communicator.connect()

        # Should be rejected
        assert not connected

        await communicator.disconnect()
