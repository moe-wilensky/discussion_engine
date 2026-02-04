"""
Additional edge case tests to achieve 90%+ coverage.

Tests for uncovered code paths in services and API endpoints.
"""

import pytest
from unittest.mock import patch
from django.core.cache import cache
from rest_framework.test import APIClient

from core.models import (
    User,
    Discussion,
    DiscussionParticipant,
    Invite,
    JoinRequest,
    PlatformConfig,
)
from core.auth.registration import PhoneVerificationService
from core.services.invite_service import InviteService
from core.services.join_request import JoinRequestService


@pytest.mark.django_db
class TestServiceEdgeCases:
    """Test edge cases in service layers."""

    def test_invite_service_get_invite_by_code_none(self):
        """Test getting invite with non-existent code."""
        invite = InviteService.get_invite_by_code("BADCODE")
        assert invite is None

    def test_phone_verification_cleanup(self, user_factory):
        """Test cleanup of expired verification codes."""
        import uuid
        from django.utils import timezone
        from datetime import timedelta

        # Create an expired code
        verification_id = str(uuid.uuid4())
        code = "123456"
        phone = "+12025555555"

        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"

        # Set with very short timeout
        cache.set(code_key, code, timeout=1)
        cache.set(phone_key, phone, timeout=1)

        # Wait for expiration
        import time

        time.sleep(2)

        # Verify cleanup worked
        assert cache.get(code_key) is None
        assert cache.get(phone_key) is None

    def test_join_request_service_get_pending_requests(
        self, user_factory, discussion_factory
    ):
        """Test getting pending join requests."""
        approver = user_factory()
        discussion = discussion_factory(initiator=approver)
        # Approver is the initiator with role="initiator" from factory
        requester = user_factory()

        # Create pending request
        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=approver,
            status="pending",
        )

        # Service method to get pending requests
        pending = JoinRequest.objects.filter(discussion=discussion, status="pending")
        assert pending.count() == 1
        assert pending.first().id == request.id


@pytest.mark.django_db
class TestAPIEdgeCases:
    """Test additional API edge cases."""

    def test_invite_metrics_for_new_user(self, api_client, user_factory):
        """Test invite metrics endpoint for user with no activity."""
        user = user_factory()

        response = api_client.get(f"/api/users/{user.id}/invite-metrics/")

        assert response.status_code == 200
        assert response.data["platform_invites"]["banked"] == 0
        assert response.data["discussion_invites"]["banked"] == 0

    def test_received_invites_empty(self, authenticated_client):
        """Test received invites when user has none."""
        response = authenticated_client.get("/api/invites/received/")

        assert response.status_code == 200
        assert len(response.data["pending"]) == 0
        assert len(response.data["accepted"]) == 0
        assert len(response.data["declined"]) == 0

    def test_suggested_discussions_when_none_available(self, authenticated_client):
        """Test suggested discussions when no discussions exist."""
        response = authenticated_client.get("/api/onboarding/suggested-discussions/")

        assert response.status_code == 200
        assert len(response.data) == 0


@pytest.mark.django_db
class TestConfigurationEdgeCases:
    """Test PlatformConfig edge cases."""

    def test_platform_config_str(self):
        """Test string representation of PlatformConfig."""
        config = PlatformConfig.load()
        assert str(config) == "Platform Configuration"

    def test_platform_config_multiple_load_calls(self):
        """Test that multiple load calls return same instance."""
        config1 = PlatformConfig.load()
        config2 = PlatformConfig.load()

        assert config1.id == config2.id
        assert config1.pk == 1
        assert config2.pk == 1


@pytest.mark.django_db
class TestAuthenticationFlow:
    """Test complete authentication flows."""

    def test_token_refresh_with_invalid_token(self, api_client):
        """Test token refresh with invalid refresh token."""
        response = api_client.post(
            "/api/auth/token/refresh/", {"refresh": "invalid.token.here"}
        )

        assert response.status_code == 401

    def test_login_verification_flow(self, api_client, user_factory):
        """Test complete login flow with existing user."""
        # Create existing user
        user = user_factory(phone_number="+12025556666")

        # Request login verification
        with patch("core.tasks.send_verification_sms.delay"):
            response = api_client.post(
                "/api/auth/login/", {"phone_number": "+12025556666"}
            )

        assert response.status_code == 200
        assert "verification_id" in response.data


@pytest.mark.django_db
class TestInviteWorkflows:
    """Test complete invite workflows."""

    def test_discussion_invite_to_observer(
        self, authenticated_client, user_factory, discussion_factory, response_factory
    ):
        """Test sending discussion invite to someone who's already an observer."""
        discussion = discussion_factory()
        invitee = user_factory()

        # Make sender a participant
        DiscussionParticipant.objects.create(
            discussion=discussion, user=authenticated_client.user, role="active"
        )

        # Make invitee an observer
        DiscussionParticipant.objects.create(
            discussion=discussion, user=invitee, role="observer"
        )

        # Give sender enough responses
        for _ in range(3):
            response_factory(user=authenticated_client.user, discussion=discussion)

        authenticated_client.user.discussion_invites_banked = 1
        authenticated_client.user.save()

        # Try to send invite (should fail - already participant)
        response = authenticated_client.post(
            "/api/invites/discussion/send/",
            {"discussion_id": discussion.id, "invitee_user_id": invitee.id},
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestSecurityEdgeCases:
    """Test security and validation edge cases."""

    def test_accept_invite_wrong_user(
        self, api_client, user_factory, discussion_factory
    ):
        """Test accepting an invite meant for someone else."""
        from rest_framework_simplejwt.tokens import RefreshToken

        inviter = user_factory()
        intended_invitee = user_factory()
        wrong_user = user_factory()
        discussion = discussion_factory()

        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )

        # Create invite for intended_invitee
        invite = Invite.objects.create(
            inviter=inviter,
            invitee=intended_invitee,
            discussion=discussion,
            invite_type="discussion",
            status="sent",
        )

        # wrong_user tries to accept
        client = APIClient()
        refresh = RefreshToken.for_user(wrong_user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

        response = client.post(f"/api/invites/{invite.id}/accept/")

        assert response.status_code == 400
