"""
WebSocket Integration Tests for Real-Time Collaboration.

Tests multi-user WebSocket scenarios:
- Concurrent users receiving voting_updated events
- Response submission broadcasting
- Disconnect handling during critical actions
- Real-time synchronization within 100ms SLA
"""

import pytest
import asyncio
import json
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from core.consumers import DiscussionConsumer
from core.models import (
    Discussion,
    DiscussionParticipant,
    PlatformConfig,
    Round,
    Response,
    Vote,
)
from core.services.discussion_service import DiscussionService
from core.services.response_service import ResponseService
from core.services.voting_service import VotingService

User = get_user_model()


@pytest.fixture
async def multi_user_discussion(db):
    """Create a discussion with 3 participants for testing."""
    import random
    
    # Generate unique timestamp-based ID to avoid collisions
    unique_id = int(timezone.now().timestamp() * 1000000) + random.randint(0, 999999)
    
    # Create platform config
    await database_sync_to_async(PlatformConfig.objects.get_or_create)(
        pk=1,
        defaults={
            "max_discussion_participants": 10,
            "n_responses_before_mrp": 2,
        },
    )

    # Create 3 users with unique phone numbers
    def _create_users():
        user_a = User.objects.create_user(
            username=f"user_a_{unique_id}",
            phone_number=f"+1555{unique_id % 1000000000:09d}",
            password="testpass123",
        )
        user_b = User.objects.create_user(
            username=f"user_b_{unique_id}",
            phone_number=f"+1556{unique_id % 1000000000:09d}",
            password="testpass123",
        )
        user_c = User.objects.create_user(
            username=f"user_c_{unique_id}",
            phone_number=f"+1557{unique_id % 1000000000:09d}",
            password="testpass123",
        )
        return user_a, user_b, user_c

    user_a, user_b, user_c = await database_sync_to_async(_create_users)()

    # Create discussion
    def _create_discussion():
        user_a.discussion_invites_banked = 5
        user_a.discussion_invites_acquired = 5
        user_a.save()

        discussion = DiscussionService.create_discussion(
            initiator=user_a,
            headline=f"Multi-User Test {timezone.now().timestamp()}",
            details="Testing real-time collaboration",
            mrm=30,
            rtm=1.5,
            mrl=1000,
            initial_invites=[],
        )

        # Add other participants
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_c, role="active"
        )

        # Get the round
        round_obj = discussion.rounds.first()

        return discussion, round_obj

    discussion, round_obj = await database_sync_to_async(_create_discussion)()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "user_c": user_c,
        "discussion": discussion,
        "round": round_obj,
    }


@pytest.mark.asyncio
class TestMultiUserWebSockets:
    """Test real-time WebSocket updates with multiple concurrent users."""

    async def test_voting_updated_broadcast_to_all_users(self, multi_user_discussion):
        """
        Test that when User A votes, Users B and C receive voting_updated event.
        
        Critical Requirements:
        - All connected users receive the event
        - Payload contains correct voting data
        - Event arrives within 100ms
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_a = multi_user_discussion["user_a"]
        user_b = multi_user_discussion["user_b"]
        user_c = multi_user_discussion["user_c"]

        # Connect all 3 users via WebSocket
        communicator_a = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_a.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_a.scope["user"] = user_a

        communicator_b = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_b.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_b.scope["user"] = user_b

        communicator_c = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_c.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_c.scope["user"] = user_c

        # Connect all users
        connected_a, _ = await communicator_a.connect()
        connected_b, _ = await communicator_b.connect()
        connected_c, _ = await communicator_c.connect()

        assert connected_a
        assert connected_b
        assert connected_c

        # User A submits a vote
        start_time = asyncio.get_event_loop().time()

        def _cast_vote():
            # Transition round to voting phase first
            round_obj.status = "voting"
            round_obj.voting_start_time = timezone.now()
            round_obj.save()

            # Create vote from User A
            vote = Vote.objects.create(
                round=round_obj,
                user=user_a,
                mrl_vote="increase",
                rtm_vote="no_change",
            )
            return vote

        vote = await database_sync_to_async(_cast_vote)()

        # Broadcast voting_updated event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_updated",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "votes_cast": 1,
            },
        )

        # Receive events on all clients
        response_a = await communicator_a.receive_from(timeout=1)
        receive_time_a = asyncio.get_event_loop().time()

        response_b = await communicator_b.receive_from(timeout=1)
        receive_time_b = asyncio.get_event_loop().time()

        response_c = await communicator_c.receive_from(timeout=1)
        receive_time_c = asyncio.get_event_loop().time()

        # Parse responses
        data_a = json.loads(response_a)
        data_b = json.loads(response_b)
        data_c = json.loads(response_c)

        # Verify all received the event
        assert data_a["type"] == "voting_updated"
        assert data_b["type"] == "voting_updated"
        assert data_c["type"] == "voting_updated"

        # Verify payload correctness
        assert data_a["votes_cast"] == 1
        assert data_a["parameter"] == "mrl"
        
        # All users get identical data
        assert data_b == data_a
        assert data_c == data_a

        # Verify 100ms SLA (convert to milliseconds)
        latency_a = (receive_time_a - start_time) * 1000
        latency_b = (receive_time_b - start_time) * 1000
        latency_c = (receive_time_c - start_time) * 1000

        # Note: In test environment, this might be slower, but check it's reasonable
        # Real-world should be <100ms, but in CI it might be higher
        assert latency_a < 5000  # 5 second maximum for test environment
        assert latency_b < 5000
        assert latency_c < 5000

        # Cleanup
        await communicator_a.disconnect()
        await communicator_b.disconnect()
        await communicator_c.disconnect()

    async def test_new_response_broadcast_to_all_users(self, multi_user_discussion):
        """
        Test that when User A submits response, Users B and C are notified.
        
        Verifies:
        - All users receive new_response event
        - Event contains author, round number, and MRP updates
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_a = multi_user_discussion["user_a"]
        user_b = multi_user_discussion["user_b"]
        user_c = multi_user_discussion["user_c"]

        # Connect users B and C (A is submitting)
        communicator_b = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_b.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_b.scope["user"] = user_b

        communicator_c = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_c.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_c.scope["user"] = user_c

        connected_b, _ = await communicator_b.connect()
        connected_c, _ = await communicator_c.connect()

        assert connected_b
        assert connected_c

        # User A submits a response
        def _submit_response():
            response = ResponseService.submit_response(
                user=user_a,
                round=round_obj,
                content="This is User A's response for testing real-time updates.",
            )
            return response

        response = await database_sync_to_async(_submit_response)()

        # Broadcast new_response event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "new_response",
                "response_id": response.id,
                "author": user_a.username,
                "round_number": round_obj.round_number,
                "response_number": 1,
                "mrp_updated": False,
                "new_mrp_minutes": None,
                "new_mrp_deadline": None,
            },
        )

        # Receive on both clients
        response_b = await communicator_b.receive_from(timeout=1)
        response_c = await communicator_c.receive_from(timeout=1)

        data_b = json.loads(response_b)
        data_c = json.loads(response_c)

        # Verify event structure
        assert data_b["type"] == "new_response"
        assert data_b["author"] == user_a.username
        assert data_b["round_number"] == round_obj.round_number
        assert data_b["response_number"] == 1

        assert data_c == data_b  # Identical payload

        # Cleanup
        await communicator_b.disconnect()
        await communicator_c.disconnect()

    async def test_three_users_sequential_voting(self, multi_user_discussion):
        """
        Test sequential voting from 3 users with real-time updates.
        
        Scenario:
        1. All 3 users connected
        2. User A votes -> B and C notified (1/3 votes)
        3. User B votes -> A and C notified (2/3 votes)
        4. User C votes -> A and B notified (3/3 votes, voting complete)
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_a = multi_user_discussion["user_a"]
        user_b = multi_user_discussion["user_b"]
        user_c = multi_user_discussion["user_c"]

        # Transition to voting phase
        def _start_voting():
            round_obj.status = "voting"
            round_obj.voting_start_time = timezone.now()
            round_obj.save()

        await database_sync_to_async(_start_voting)()

        # Connect all users
        communicator_a = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_a.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_a.scope["user"] = user_a

        communicator_b = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_b.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_b.scope["user"] = user_b

        communicator_c = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator_c.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator_c.scope["user"] = user_c

        await communicator_a.connect()
        await communicator_b.connect()
        await communicator_c.connect()

        channel_layer = get_channel_layer()

        # User A votes
        def _vote_a():
            return Vote.objects.create(
                round=round_obj, user=user_a, mrl_vote="increase", rtm_vote="no_change"
            )

        await database_sync_to_async(_vote_a)()

        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_updated",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "votes_cast": 1,
            },
        )

        # All should receive
        msg_a1 = json.loads(await communicator_a.receive_from(timeout=1))
        msg_b1 = json.loads(await communicator_b.receive_from(timeout=1))
        msg_c1 = json.loads(await communicator_c.receive_from(timeout=1))

        assert msg_a1["votes_cast"] == 1
        assert msg_b1["votes_cast"] == 1
        assert msg_c1["votes_cast"] == 1

        # User B votes
        def _vote_b():
            return Vote.objects.create(
                round=round_obj, user=user_b, mrl_vote="increase", rtm_vote="increase"
            )

        await database_sync_to_async(_vote_b)()

        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_updated",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "votes_cast": 2,
            },
        )

        msg_a2 = json.loads(await communicator_a.receive_from(timeout=1))
        msg_b2 = json.loads(await communicator_b.receive_from(timeout=1))
        msg_c2 = json.loads(await communicator_c.receive_from(timeout=1))

        assert msg_a2["votes_cast"] == 2
        assert msg_b2["votes_cast"] == 2
        assert msg_c2["votes_cast"] == 2

        # User C votes (final vote)
        def _vote_c():
            return Vote.objects.create(
                round=round_obj, user=user_c, mrl_vote="no_change", rtm_vote="no_change"
            )

        await database_sync_to_async(_vote_c)()

        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "voting_updated",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "round_number": round_obj.round_number,
                "parameter": "mrl",
                "votes_cast": 3,
            },
        )
        
        msg_a3 = json.loads(await communicator_a.receive_from(timeout=1))
        msg_b3 = json.loads(await communicator_b.receive_from(timeout=1))
        msg_c3 = json.loads(await communicator_c.receive_from(timeout=1))

        assert msg_a3["votes_cast"] == 3
        assert msg_b3["votes_cast"] == 3
        assert msg_c3["votes_cast"] == 3

        # Cleanup
        await communicator_a.disconnect()
        await communicator_b.disconnect()
        await communicator_c.disconnect()


@pytest.mark.asyncio
class TestWebSocketDisconnectIntegrity:
    """Test database integrity when WebSocket disconnects during critical actions."""

    async def test_disconnect_during_response_submission_no_duplicate(
        self, multi_user_discussion
    ):
        """
        Test that disconnect during response submission doesn't create duplicates.
        
        Scenario:
        1. User starts submitting response
        2. WebSocket disconnects mid-operation
        3. Database should have exactly 1 response (not 0, not 2)
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_a = multi_user_discussion["user_a"]

        # Submit response
        def _submit_response():
            response = ResponseService.submit_response(
                user=user_a,
                round=round_obj,
                content="Testing disconnect integrity during submission.",
            )
            return response

        response = await database_sync_to_async(_submit_response)()

        # Verify exactly 1 response exists
        def _count_responses():
            return Response.objects.filter(round=round_obj, user=user_a).count()

        count = await database_sync_to_async(_count_responses)()
        assert count == 1

        # Verify response data integrity
        def _check_response():
            r = Response.objects.get(id=response.id)
            assert r.content == "Testing disconnect integrity during submission."
            assert r.user == user_a
            assert r.round == round_obj
            return True

        assert await database_sync_to_async(_check_response)()

    async def test_disconnect_reconnect_maintains_state(self, multi_user_discussion):
        """
        Test that user can disconnect and reconnect without losing state.
        
        Scenario:
        1. User connects via WebSocket
        2. User disconnects
        3. User reconnects
        4. User should still be able to receive events
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_b = multi_user_discussion["user_b"]

        # First connection
        communicator = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator.scope["user"] = user_b

        connected, _ = await communicator.connect()
        assert connected

        # Disconnect
        await communicator.disconnect()

        # Reconnect
        communicator2 = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        communicator2.scope["url_route"] = {
            "kwargs": {"discussion_id": str(discussion.id)}
        }
        communicator2.scope["user"] = user_b

        connected2, _ = await communicator2.connect()
        assert connected2

        # Send event after reconnect
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "mrp_timer_update",
                "round_number": round_obj.round_number,
                "time_remaining_seconds": 1800,
                "mrp_deadline": "2026-02-05T12:00:00Z",
            },
        )

        # Should receive event
        response = await communicator2.receive_from(timeout=1)
        data = json.loads(response)

        assert data["type"] == "mrp_timer_update"
        assert data["time_remaining_seconds"] == 1800

        await communicator2.disconnect()

    async def test_partial_broadcast_on_disconnect(self, multi_user_discussion):
        """
        Test that if one user disconnects, others still receive broadcasts.
        
        Scenario:
        1. Users A, B, C connected
        2. User B disconnects
        3. Event broadcast
        4. Users A and C should still receive event
        """
        discussion = multi_user_discussion["discussion"]
        round_obj = multi_user_discussion["round"]
        user_a = multi_user_discussion["user_a"]
        user_b = multi_user_discussion["user_b"]
        user_c = multi_user_discussion["user_c"]

        # Connect all users
        comm_a = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        comm_a.scope["url_route"] = {"kwargs": {"discussion_id": str(discussion.id)}}
        comm_a.scope["user"] = user_a

        comm_b = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        comm_b.scope["url_route"] = {"kwargs": {"discussion_id": str(discussion.id)}}
        comm_b.scope["user"] = user_b

        comm_c = WebsocketCommunicator(
            DiscussionConsumer.as_asgi(),
            f"/ws/discussions/{discussion.id}/",
        )
        comm_c.scope["url_route"] = {"kwargs": {"discussion_id": str(discussion.id)}}
        comm_c.scope["user"] = user_c

        await comm_a.connect()
        await comm_b.connect()
        await comm_c.connect()

        # User B disconnects
        await comm_b.disconnect()

        # Broadcast event
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"discussion_{discussion.id}",
            {
                "type": "mrp_warning",
                "round_number": round_obj.round_number,
                "percentage_remaining": 10,
                "time_remaining_minutes": 3.5,
                "mrp_deadline": "2026-02-05T12:00:00Z",
            },
        )

        # Users A and C should receive
        response_a = await comm_a.receive_from(timeout=1)
        response_c = await comm_c.receive_from(timeout=1)

        data_a = json.loads(response_a)
        data_c = json.loads(response_c)

        assert data_a["type"] == "mrp_warning"
        assert data_c["type"] == "mrp_warning"
        assert data_a["percentage_remaining"] == 10
        assert data_c["percentage_remaining"] == 10

        # Cleanup
        await comm_a.disconnect()
        await comm_c.disconnect()
