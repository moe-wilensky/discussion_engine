"""
Tests for rejoin discussion API endpoint.

Tests the POST /api/discussions/{discussion_id}/rejoin/ endpoint
for various observer scenarios.
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    User,
    Discussion,
    Round,
    DiscussionParticipant,
    PlatformConfig,
)
from core.services.observer_service import ObserverService


@pytest.mark.django_db
class TestRejoinDiscussionAPI:
    """Test rejoin discussion API endpoint"""

    @pytest.fixture
    def setup_discussion(self):
        """Create a discussion with rounds and participants"""
        config = PlatformConfig.load()

        # Create users
        initiator = User.objects.create_user(
            username="initiator", phone_number="+11234567890", password="test123"
        )
        observer_user = User.objects.create_user(
            username="observer", phone_number="+11234567891", password="test123"
        )
        active_user = User.objects.create_user(
            username="active", phone_number="+11234567892", password="test123"
        )

        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Testing rejoin functionality",
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=initiator,
        )

        # Create participants
        DiscussionParticipant.objects.create(
            discussion=discussion, user=initiator, role="initiator"
        )
        observer_participant = DiscussionParticipant.objects.create(
            discussion=discussion, user=observer_user, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=active_user, role="active"
        )

        # Create round
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
            start_time=timezone.now() - timedelta(minutes=30),
        )

        return {
            "config": config,
            "initiator": initiator,
            "observer_user": observer_user,
            "active_user": active_user,
            "discussion": discussion,
            "round": round_obj,
            "observer_participant": observer_participant,
        }

    def test_rejoin_not_authenticated(self, setup_discussion):
        """Test that unauthenticated users cannot rejoin"""
        data = setup_discussion
        discussion = data["discussion"]

        client = APIClient()
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_rejoin_not_participant(self, setup_discussion):
        """Test that non-participants cannot rejoin"""
        data = setup_discussion
        discussion = data["discussion"]

        # Create a new user who is not a participant
        non_participant = User.objects.create_user(
            username="outsider", phone_number="+11234567893", password="test123"
        )

        client = APIClient()
        client.force_authenticate(user=non_participant)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not a participant" in str(response.data).lower()

    def test_rejoin_already_active(self, setup_discussion):
        """Test that already active participants cannot rejoin"""
        data = setup_discussion
        discussion = data["discussion"]
        active_user = data["active_user"]

        client = APIClient()
        client.force_authenticate(user=active_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already an active participant" in str(response.data).lower()

    def test_rejoin_no_active_round(self, setup_discussion):
        """Test that users cannot rejoin when there's no active round"""
        data = setup_discussion
        discussion = data["discussion"]
        observer_user = data["observer_user"]
        observer_participant = data["observer_participant"]
        round_obj = data["round"]

        # Move user to observer status
        ObserverService.move_to_observer(
            observer_participant, "mrp_expired", posted_in_round=False
        )

        # End the round
        round_obj.status = "completed"
        round_obj.save()

        client = APIClient()
        client.force_authenticate(user=observer_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no active round" in str(response.data).lower()

    def test_rejoin_permanent_observer(self, setup_discussion):
        """Test that permanent observers cannot rejoin"""
        data = setup_discussion
        discussion = data["discussion"]
        observer_user = data["observer_user"]
        observer_participant = data["observer_participant"]

        # Make user permanent observer
        ObserverService.make_permanent_observer(
            observer_participant, "repeated_violations"
        )

        client = APIClient()
        client.force_authenticate(user=observer_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "permanent observer" in str(response.data).lower()

    def test_rejoin_too_soon(self, setup_discussion):
        """Test that users cannot rejoin before wait period ends"""
        data = setup_discussion
        discussion = data["discussion"]
        observer_user = data["observer_user"]
        observer_participant = data["observer_participant"]

        # Move user to observer status just now
        ObserverService.move_to_observer(
            observer_participant, "mutual_removal", posted_in_round=False
        )

        client = APIClient()
        client.force_authenticate(user=observer_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "wait" in str(response.data).lower()

    def test_rejoin_successful_after_wait(self, setup_discussion):
        """Test successful rejoin after wait period"""
        data = setup_discussion
        discussion = data["discussion"]
        observer_user = data["observer_user"]
        observer_participant = data["observer_participant"]
        round_obj = data["round"]

        # Move user to observer status 61 minutes ago (1 MRP = 60 minutes)
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = timezone.now() - timedelta(minutes=61)
        observer_participant.observer_reason = "mutual_removal"
        observer_participant.posted_in_round_when_removed = False
        observer_participant.save()

        client = APIClient()
        client.force_authenticate(user=observer_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["rejoined"] is True
        assert response.data["new_role"] == "active"

        # Verify participant was updated
        observer_participant.refresh_from_db()
        assert observer_participant.role == "active"
        assert observer_participant.observer_since is None
        assert observer_participant.observer_reason is None

    def test_rejoin_successful_next_round_simple_case(self, setup_discussion):
        """Test successful rejoin in later rounds (simplified test)"""
        data = setup_discussion
        discussion = data["discussion"]
        observer_user = data["observer_user"]
        observer_participant = data["observer_participant"]
        round1 = data["round"]

        # Update round 1 start time to be in the past and mark as completed
        round1.start_time = timezone.now() - timedelta(hours=3)
        round1.status = "completed"
        round1.save()

        # Move user to observer in round 1 due to MRP expiration (65 minutes after round started)
        removal_time = round1.start_time + timedelta(minutes=65)
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = removal_time
        observer_participant.observer_reason = "mrp_expired"
        observer_participant.posted_in_round_when_removed = False
        observer_participant.save()

        # Create round 2 and wait long enough in round 2
        Round.objects.create(
            discussion=discussion,
            round_number=2,
            status="completed",
            final_mrp_minutes=60.0,
            start_time=timezone.now() - timedelta(hours=2),
        )

        # Create round 3 (well past the wait period)
        Round.objects.create(
            discussion=discussion,
            round_number=3,
            status="in_progress",
            final_mrp_minutes=60.0,
            start_time=timezone.now() - timedelta(hours=1),
        )

        client = APIClient()
        client.force_authenticate(user=observer_user)
        response = client.post(f"/api/discussions/{discussion.id}/rejoin/")

        # Should be able to rejoin after multiple rounds have passed
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rejoined"] is True
        assert response.data["new_role"] == "active"

    def test_rejoin_invalid_discussion_id(self):
        """Test rejoin with invalid discussion ID"""
        user = User.objects.create_user(
            username="test", phone_number="+11234567890", password="test123"
        )

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post("/api/discussions/99999/rejoin/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
