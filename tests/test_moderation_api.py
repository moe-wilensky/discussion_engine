"""Tests for moderation API endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient
from core.models import (
    User, Discussion, DiscussionParticipant, Round, PlatformConfig,
    ModerationAction,
)


class TestMutualRemovalAPI(TestCase):
    """Tests for the mutual removal API endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.initiator = User.objects.create_user(
            username="initiator", phone_number="+15551111111", password="testpass123"
        )
        self.target = User.objects.create_user(
            username="target", phone_number="+15552222222", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Details",
            initiator=self.initiator,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.initiator, role="initiator"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.target, role="active"
        )
        self.url = f"/api/discussions/{self.discussion.id}/mutual-removal/"

    def test_requires_authentication(self):
        response = self.client.post(self.url, {"target_user_id": str(self.target.id)})
        assert response.status_code == 401

    def test_missing_target_user_id(self):
        self.client.force_authenticate(user=self.initiator)
        response = self.client.post(self.url, {})
        assert response.status_code == 400
        assert "target_user_id" in response.json()["error"]

    def test_target_user_not_found(self):
        self.client.force_authenticate(user=self.initiator)
        response = self.client.post(self.url, {"target_user_id": "999999"})
        assert response.status_code == 404

    def test_no_active_round(self):
        self.round.status = "completed"
        self.round.save()
        self.client.force_authenticate(user=self.initiator)
        response = self.client.post(self.url, {"target_user_id": str(self.target.id)})
        assert response.status_code == 400
        assert "No active round" in response.json()["error"]

    def test_discussion_not_found(self):
        self.client.force_authenticate(user=self.initiator)
        response = self.client.post("/api/discussions/99999/mutual-removal/", {
            "target_user_id": str(self.target.id)
        })
        assert response.status_code == 404


class TestModerationStatusAPI(TestCase):
    """Tests for the moderation status API endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", phone_number="+15552222222", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.other_user, role="active"
        )
        self.url = f"/api/discussions/{self.discussion.id}/moderation-status/"

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        assert response.status_code == 401

    def test_non_participant_gets_404(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15553333333"
        )
        self.client.force_authenticate(user=outsider)
        response = self.client.get(self.url)
        assert response.status_code == 404

    def test_active_participant_gets_status(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == 200
        data = response.json()
        assert "user_removal_count" in data
        assert "user_times_removed" in data
        assert "can_initiate_removal" in data
        assert "escalation_status" in data
        assert "moderation_history" in data

    def test_can_initiate_removal_with_other_active(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        data = response.json()
        assert data["can_initiate_removal"] is True

    def test_moderation_history_includes_actions(self):
        ModerationAction.objects.create(
            discussion=self.discussion,
            initiator=self.user,
            target=self.other_user,
            action_type="mutual_removal",
            round_occurred=self.round,
            is_permanent=False,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        data = response.json()
        assert len(data["moderation_history"]) == 1
        assert data["moderation_history"][0]["action_type"] == "mutual_removal"
