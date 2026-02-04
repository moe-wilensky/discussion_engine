"""
Comprehensive API integration tests.

Tests complete flows end-to-end including authentication, invites, and join requests.
"""

import pytest
from unittest.mock import patch
from django.core.cache import cache

from core.models import User, PlatformConfig, Invite, DiscussionParticipant
from core.auth.registration import PhoneVerificationService
from core.services.invite_service import InviteService


@pytest.mark.django_db
class TestCompleteRegistrationFlow:
    """Test complete user registration flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        cache.clear()
        PlatformConfig.objects.get_or_create(pk=1)

    def test_full_registration_with_invite(
        self, api_client, user_factory, discussion_factory, response_factory
    ):
        """Test complete registration flow from verification to authenticated user."""
        # Step 1: Existing user creates invite
        inviter = user_factory()
        inviter.platform_invites_banked = 1
        inviter.save()

        discussion = discussion_factory()
        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter, discussion=discussion)

        invite, invite_code = InviteService.send_platform_invite(inviter)

        # Step 2: New user requests verification
        with patch("core.tasks.send_verification_sms.delay"):
            response = api_client.post(
                "/api/auth/register/request-verification/",
                {"phone_number": "+12025558888"},
            )

        assert response.status_code == 200
        verification_id = response.data["verification_id"]

        # Step 3: Get code from cache (in real scenario, user receives via SMS)
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        code = cache.get(code_key)

        # Step 4: Complete registration with invite code
        response = api_client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": verification_id,
                "code": code,
                "invite_code": invite_code,
                "username": "newuser123",
            },
        )

        assert response.status_code == 201
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]

        # Step 5: Verify user was created and invite accepted
        new_user = User.objects.get(username="newuser123")
        assert new_user.phone_number == "+12025558888"

        invite.refresh_from_db()
        assert invite.status == "accepted"
        assert invite.invitee == new_user

        # Step 6: Verify new user has starting invites
        assert new_user.platform_invites_banked == config.new_user_platform_invites

        # Step 7: Test authentication with token
        access_token = response.data["tokens"]["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = api_client.get("/api/invites/me/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestCompleteInviteFlow:
    """Test complete invite acceptance flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_full_discussion_invite_flow(
        self, authenticated_client, user_factory, discussion_factory, response_factory
    ):
        """Test complete discussion invite flow."""
        inviter = authenticated_client.user
        invitee = user_factory()
        discussion = discussion_factory()

        # Step 1: Make inviter participant
        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )

        # Step 2: Give inviter invites and responses
        inviter.discussion_invites_banked = 1
        inviter.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter, discussion=discussion)

        # Step 3: Send discussion invite
        with patch("core.tasks.send_invite_notification.delay"):
            response = authenticated_client.post(
                "/api/invites/discussion/send/",
                {
                    "discussion_id": str(discussion.id),
                    "invitee_user_id": str(invitee.id),
                },
            )

        assert response.status_code == 200
        invite_id = response.data["invite_id"]

        # Step 4: Invitee views received invites
        # (Switch to invitee's session)
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        invitee_client = APIClient()
        refresh = RefreshToken.for_user(invitee)
        invitee_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}"
        )

        response = invitee_client.get("/api/invites/received/")
        assert response.status_code == 200
        assert len(response.data["pending"]) == 1

        # Step 5: Invitee accepts invite
        response = invitee_client.post(f"/api/invites/{invite_id}/accept/")
        assert response.status_code == 200

        # Step 6: Verify invitee is now participant
        assert DiscussionParticipant.objects.filter(
            discussion=discussion, user=invitee, role="active"
        ).exists()


@pytest.mark.django_db
class TestCompleteJoinRequestFlow:
    """Test complete join request flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_full_join_request_flow(self, api_client, user_factory, discussion_factory):
        """Test complete join request from request to approval."""
        requester = user_factory()
        approver = user_factory()
        discussion = discussion_factory()

        # Setup: Approver is participant
        DiscussionParticipant.objects.create(
            discussion=discussion, user=approver, role="active"
        )

        # Step 1: Requester creates join request
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        requester_client = APIClient()
        refresh = RefreshToken.for_user(requester)
        requester_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}"
        )

        with patch("core.tasks.send_join_request_notification.delay"):
            response = requester_client.post(
                f"/api/discussions/{discussion.id}/join-request/",
                {"message": "I'd love to participate"},
            )

        assert response.status_code == 201
        request_id = response.data["id"]

        # Step 2: Approver views join requests
        approver_client = APIClient()
        refresh = RefreshToken.for_user(approver)
        approver_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}"
        )

        response = approver_client.get(
            f"/api/discussions/{discussion.id}/join-requests/"
        )
        assert response.status_code == 200
        assert len(response.data["pending"]) == 1

        # Step 3: Approver approves request
        with patch("core.tasks.send_join_request_approved_notification.delay"):
            response = approver_client.post(f"/api/join-requests/{request_id}/approve/")

        assert response.status_code == 200

        # Step 4: Verify requester is now participant
        assert DiscussionParticipant.objects.filter(
            discussion=discussion, user=requester, role="active"
        ).exists()


@pytest.mark.django_db
class TestAuthenticationRequired:
    """Test authentication requirements on protected endpoints."""

    def test_protected_endpoints_require_auth(self, api_client):
        """Test that protected endpoints reject unauthenticated requests."""
        protected_endpoints = [
            "/api/invites/me/",
            "/api/invites/platform/send/",
            "/api/invites/received/",
            "/api/onboarding/tutorial/",
            "/api/onboarding/tutorial/complete/",
        ]

        for endpoint in protected_endpoints:
            response = api_client.get(endpoint)
            assert response.status_code in [
                401,
                403,
            ], f"Endpoint {endpoint} should require auth"


@pytest.mark.django_db
class TestPermissionChecks:
    """Test permission checks on endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_cannot_send_invite_without_participation(
        self, authenticated_client, user_factory, discussion_factory
    ):
        """Test cannot send discussion invite if not participant."""
        discussion = discussion_factory()
        invitee = user_factory()

        # User is not participant
        response = authenticated_client.post(
            "/api/invites/discussion/send/",
            {"discussion_id": str(discussion.id), "invitee_user_id": str(invitee.id)},
        )

        assert response.status_code == 400
        assert "active participants" in response.data["error"].lower()

    def test_cannot_view_join_requests_if_not_participant(
        self, authenticated_client, discussion_factory
    ):
        """Test cannot view join requests if not participant."""
        discussion = discussion_factory()

        response = authenticated_client.get(
            f"/api/discussions/{discussion.id}/join-requests/"
        )

        assert response.status_code == 403
