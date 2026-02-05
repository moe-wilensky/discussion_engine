"""
Tests for WebSocket event handlers.

Tests that all WebSocket events are properly broadcast and received:
- voting_updated
- voting_closed
- parameter_changed
- user_removed
- mrp_timer_update
"""

import pytest
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
import json

from core.consumers import DiscussionConsumer
from core.models import Discussion, DiscussionParticipant, PlatformConfig, Round
from core.services.discussion_service import DiscussionService

User = get_user_model()


@pytest.fixture
async def event_test_data(db):
    """Set up test data for event testing."""
    import random

    # Create platform config
    await database_sync_to_async(PlatformConfig.objects.get_or_create)(
        pk=1,
        defaults={
            "max_discussion_participants": 10,
            "responses_to_unlock_invites": 5,
        },
    )

    # Create test users
    unique_id = random.randint(10000, 99999)
    user1 = await database_sync_to_async(User.objects.create_user)(
        username=f"participant1_{unique_id}", phone_number=f"+1123456{unique_id:05d}"
    )
    user2 = await database_sync_to_async(User.objects.create_user)(
        username=f"participant2_{unique_id}", phone_number=f"+1223456{unique_id:05d}"
    )

    # Give user1 discussion invites
    def _give_invites():
        user1.discussion_invites_banked = 5
        user1.discussion_invites_acquired = 5
        user1.save()

    await database_sync_to_async(_give_invites)()

    # Create a discussion
    def _create_discussion():
        discussion = DiscussionService.create_discussion(
            initiator=user1,
            headline=f"Test Discussion {unique_id}",
            details=f"Test details {unique_id}",
            mrm=30,
            rtm=2.0,
            mrl=2000,
            initial_invites=[],
        )

        # Add user2 as participant
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user2,
            role='active'
        )

        # Get first round
        round_obj = discussion.rounds.first()

        return discussion, round_obj

    discussion, round_obj = await database_sync_to_async(_create_discussion)()

    return {
        "user1": user1,
        "user2": user2,
        "discussion": discussion,
        "round": round_obj,
    }


@pytest.mark.asyncio
class TestWebSocketEvents:
    """Test WebSocket event broadcasting."""

    async def test_mrp_timer_update_event(self, event_test_data):
        """Test that mrp_timer_update events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        round_obj = event_test_data["round"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a timer update event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "mrp_timer_update",
                "round_number": round_obj.round_number,
                "time_remaining_seconds": 300,
                "mrp_deadline": "2026-02-05T12:00:00Z",
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "mrp_timer_update"
        assert data["round_number"] == round_obj.round_number
        assert data["time_remaining_seconds"] == 300
        assert data["mrp_deadline"] == "2026-02-05T12:00:00Z"

        await communicator.disconnect()

    async def test_voting_updated_event(self, event_test_data):
        """Test that voting_updated events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        round_obj = event_test_data["round"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a voting_updated event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_updated",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "votes_cast": 3,
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "voting_updated"
        assert data["round_number"] == round_obj.round_number
        assert data["parameter"] == "mrl"
        assert data["votes_cast"] == 3

        await communicator.disconnect()

    async def test_voting_closed_event(self, event_test_data):
        """Test that voting_closed events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        round_obj = event_test_data["round"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a voting_closed event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_closed",
                "round_number": round_obj.round_number,
                "mrl_result": "increased",
                "rtm_result": "decreased",
                "users_removed": [],
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "voting_closed"
        assert data["round_number"] == round_obj.round_number
        assert data["mrl_result"] == "increased"
        assert data["rtm_result"] == "decreased"
        assert data["users_removed"] == []

        await communicator.disconnect()

    async def test_parameter_changed_event(self, event_test_data):
        """Test that parameter_changed events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a parameter_changed event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "parameter_changed",
                "parameter": "mrl",
                "old_value": "2000",
                "new_value": "2500",
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "parameter_changed"
        assert data["parameter"] == "mrl"
        assert data["old_value"] == "2000"
        assert data["new_value"] == "2500"

        await communicator.disconnect()

    async def test_user_removed_event(self, event_test_data):
        """Test that user_removed events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        user2 = event_test_data["user2"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a user_removed event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "user_removed",
                "user_id": user2.id,
                "username": user2.username,
                "reason": "vote_based_removal",
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "user_removed"
        assert data["user_id"] == user2.id
        assert data["username"] == user2.username
        assert data["reason"] == "vote_based_removal"

        await communicator.disconnect()

    async def test_new_response_event_with_round_number(self, event_test_data):
        """Test that new_response events include round_number for API calls."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        round_obj = event_test_data["round"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a new_response event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "new_response",
                "response_id": "test-uuid",
                "author": user1.username,
                "round_number": round_obj.round_number,
                "response_number": 1,
                "mrp_updated": True,
                "new_mrp_minutes": 35.5,
                "new_mrp_deadline": "2026-02-05T12:30:00Z",
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure includes round_number for API calls
        assert data["type"] == "new_response"
        assert data["round_number"] == round_obj.round_number
        assert data["author"] == user1.username
        assert data["mrp_updated"] is True

        await communicator.disconnect()

    async def test_voting_started_event(self, event_test_data):
        """Test that voting_started events are properly received."""
        discussion = event_test_data["discussion"]
        user1 = event_test_data["user1"]
        round_obj = event_test_data["round"]

        # Connect WebSocket
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user1

        connected, _ = await communicator.connect()
        assert connected

        # Broadcast a voting_started event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_started",
                "round_number": round_obj.round_number,
                "voting_closes_at": "2026-02-06T12:00:00Z",
            }
        )

        # Receive the event
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        # Verify event structure
        assert data["type"] == "voting_started"
        assert data["round_number"] == round_obj.round_number
        assert data["voting_closes_at"] == "2026-02-06T12:00:00Z"

        await communicator.disconnect()
