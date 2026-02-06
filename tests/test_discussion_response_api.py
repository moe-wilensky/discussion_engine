"""Tests for discussion and response API endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient
from core.models import (
    User, Discussion, DiscussionParticipant, Round, Response as DiscResponse,
    PlatformConfig,
)


class TestGetPresetsAPI(TestCase):
    """Tests for the GET /api/discussions/presets/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/discussions/presets/")
        assert response.status_code == 401

    def test_returns_presets(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/presets/")
        assert response.status_code == 200
        assert "presets" in response.json()
        assert len(response.json()["presets"]) > 0


class TestPreviewParametersAPI(TestCase):
    """Tests for the POST /api/discussions/preview-parameters/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/discussions/preview-parameters/", {})
        assert response.status_code == 401

    def test_valid_parameters(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/preview-parameters/",
            {"mrm": 30, "rtm": 2.0, "mrl": 2000},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True


class TestCreateDiscussionAPI(TestCase):
    """Tests for the POST /api/discussions/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        PlatformConfig.load()

    def test_requires_authentication(self):
        response = self.client.post("/api/discussions/create/", {})
        assert response.status_code == 401

    def test_create_with_preset(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/create/",
            {
                "headline": "Test Discussion",
                "details": "Full details here",
                "preset": "thoughtful_discussion",
            },
            format="json",
        )
        assert response.status_code == 201
        assert "discussion_id" in response.json()

    def test_create_with_invalid_preset(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/create/",
            {
                "headline": "Test Discussion",
                "details": "Full details here",
                "preset": "nonexistent_preset",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_create_missing_custom_params(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/create/",
            {
                "headline": "Test Discussion",
                "details": "Full details here",
                "mrm_minutes": 30,
                # missing rtm and mrl
            },
            format="json",
        )
        assert response.status_code == 400

    def test_create_with_nonexistent_invite(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/create/",
            {
                "headline": "Test Discussion",
                "details": "Full details here",
                "preset": "thoughtful_discussion",
                "initial_invites": [999999],
            },
            format="json",
        )
        assert response.status_code == 400


class TestGetDiscussionAPI(TestCase):
    """Tests for the GET /api/discussions/{id}/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )

    def test_returns_discussion_detail(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/discussions/{self.discussion.id}/")
        assert response.status_code == 200

    def test_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/99999/")
        assert response.status_code == 404

    def test_non_participant_forbidden(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15552222222"
        )
        self.client.force_authenticate(user=outsider)
        response = self.client.get(f"/api/discussions/{self.discussion.id}/")
        assert response.status_code == 403


class TestListDiscussionsAPI(TestCase):
    """Tests for the GET /api/discussions/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )

    def test_list_active(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/", {"type": "active"})
        assert response.status_code == 200
        assert "discussions" in response.json()

    def test_list_observable(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/", {"type": "observable"})
        assert response.status_code == 200


class TestMyDiscussionStatesAPI(TestCase):
    """Tests for the GET /api/discussions/my-states/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
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
            discussion=self.discussion, user=self.user, role="active"
        )

    def test_returns_discussion_states(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/my-states/")
        assert response.status_code == 200
        data = response.json()
        assert "discussions" in data
        assert "credits" in data
        assert len(data["discussions"]) == 1

    def test_active_needs_response_status(self):
        """User with no response in active round gets needs-response status."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/my-states/")
        data = response.json()
        disc = data["discussions"][0]
        # User hasn't responded yet in active round
        assert disc["ui_status"] == "active-needs-response"

    def test_waiting_status_after_response(self):
        """User who has responded gets waiting status."""
        DiscResponse.objects.create(
            round=self.round, user=self.user, content="My response"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/my-states/")
        data = response.json()
        disc = data["discussions"][0]
        assert disc["ui_status"] == "waiting"

    def test_voting_available_status(self):
        """User in voting phase gets voting-available status."""
        self.round.status = "voting"
        self.round.save()
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/my-states/")
        data = response.json()
        disc = data["discussions"][0]
        assert disc["ui_status"] == "voting-available"

    def test_observer_status(self):
        """Observer gets observer status."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion, user=self.user
        )
        participant.role = "observer"
        participant.save()
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/discussions/my-states/")
        data = response.json()
        disc = data["discussions"][0]
        assert disc["ui_status"] == "observer"


class TestListResponsesAPI(TestCase):
    """Tests for the GET /api/discussions/{id}/rounds/{num}/responses/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
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

    def test_returns_responses(self):
        DiscResponse.objects.create(
            round=self.round, user=self.user, content="Test response"
        )
        self.client.force_authenticate(user=self.user)
        url = f"/api/discussions/{self.discussion.id}/rounds/1/responses/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert "responses" in response.json()
        assert len(response.json()["responses"]) == 1

    def test_round_not_found(self):
        self.client.force_authenticate(user=self.user)
        url = f"/api/discussions/{self.discussion.id}/rounds/99/responses/"
        response = self.client.get(url)
        assert response.status_code == 404

    def test_non_participant_forbidden(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15552222222"
        )
        self.client.force_authenticate(user=outsider)
        url = f"/api/discussions/{self.discussion.id}/rounds/1/responses/"
        response = self.client.get(url)
        assert response.status_code == 403


class TestRespondToDiscussionAPI(TestCase):
    """Tests for the POST /api/discussions/{id}/respond/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
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
        self.url = f"/api/discussions/{self.discussion.id}/respond/"

    def test_submit_response(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, {"response_text": "My response text"}, format="json"
        )
        assert response.status_code == 201

    def test_discussion_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/discussions/99999/respond/",
            {"response_text": "text"},
            format="json",
        )
        assert response.status_code == 404

    def test_non_active_participant_forbidden(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15552222222"
        )
        self.client.force_authenticate(user=outsider)
        response = self.client.post(
            self.url, {"response_text": "text"}, format="json"
        )
        assert response.status_code == 403

    def test_no_active_round(self):
        self.round.status = "completed"
        self.round.save()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, {"response_text": "text"}, format="json"
        )
        assert response.status_code == 400

    def test_empty_response_text(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, {"response_text": ""}, format="json"
        )
        assert response.status_code == 400


class TestEditResponseAPI(TestCase):
    """Tests for the PATCH /api/responses/{id}/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
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
        self.response_obj = DiscResponse.objects.create(
            round=self.round, user=self.user, content="Original content"
        )

    def test_edit_own_response(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/responses/{self.response_obj.id}/",
            {"content": "Original contenT"},
            format="json",
        )
        assert response.status_code == 200
        assert "edit_number" in response.json()

    def test_edit_response_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            "/api/responses/999999/",
            {"content": "Updated"},
            format="json",
        )
        assert response.status_code == 404

    def test_cannot_edit_others_response(self):
        other_user = User.objects.create_user(
            username="other", phone_number="+15552222222"
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.patch(
            f"/api/responses/{self.response_obj.id}/",
            {"content": "Updated"},
            format="json",
        )
        assert response.status_code == 403


class TestCreateQuoteAPI(TestCase):
    """Tests for the POST /api/responses/{id}/quote/ endpoint."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
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
        self.response_obj = DiscResponse.objects.create(
            round=self.round, user=self.user, content="This is the full response text"
        )

    def test_create_quote(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/responses/{self.response_obj.id}/quote/",
            {
                "quoted_text": "full response",
                "start_index": 12,
                "end_index": 25,
            },
            format="json",
        )
        assert response.status_code == 200
        assert "quote_markdown" in response.json()

    def test_quote_response_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/responses/999999/quote/",
            {"quoted_text": "text", "start_index": 0, "end_index": 4},
            format="json",
        )
        assert response.status_code == 404
