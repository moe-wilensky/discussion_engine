"""
Tests for API error handling paths.

Comprehensive coverage of error scenarios across all API endpoints.
"""

import pytest
from unittest.mock import patch
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import User, Discussion, DiscussionParticipant, Invite, JoinRequest
from core.auth.registration import PhoneVerificationService
from core.services.invite_service import InviteService


@pytest.mark.django_db
class TestAuthAPIErrors:
    """Test error handling in authentication endpoints."""

    def test_request_verification_invalid_phone(self, api_client):
        """Test verification request with invalid phone format."""
        response = api_client.post(
            "/api/auth/register/request-verification/", {"phone_number": "invalid"}
        )
        assert response.status_code == 400

    def test_verify_code_invalid_verification_id(self, api_client):
        """Test code verification with non-existent verification ID."""
        response = api_client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": "bad-uuid-format",
                "code": "123456",
                "username": "testuser",
            },
        )
        assert response.status_code == 400

    def test_verify_code_invalid_invite_code(self, api_client):
        """Test registration with invalid invite code."""
        import uuid

        verification_id = str(uuid.uuid4())
        code = "123456"
        phone = "+12025551111"

        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"

        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)

        response = api_client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": verification_id,
                "code": code,
                "invite_code": "BADCODE",
                "username": "testuser",
            },
        )

        assert response.status_code == 400
        assert "invite" in response.data["error"].lower()


@pytest.mark.django_db
class TestInviteAPIErrors:
    """Test error handling in invite endpoints."""

    def test_send_platform_invite_insufficient_responses(
        self, authenticated_client, user_factory
    ):
        """Test sending platform invite without enough responses."""
        response = authenticated_client.post("/api/invites/platform/send/")

        assert response.status_code == 400
        assert "responses" in response.data["error"].lower()

    def test_send_discussion_invite_invalid_discussion(
        self, authenticated_client, user_factory
    ):
        """Test sending discussion invite with invalid discussion ID."""
        invitee = user_factory()

        response = authenticated_client.post(
            "/api/invites/discussion/send/",
            {"discussion_id": 999999, "invitee_user_id": invitee.id},
        )

        assert response.status_code == 404

    def test_send_discussion_invite_invalid_user(
        self, authenticated_client, discussion_factory
    ):
        """Test sending discussion invite with invalid user ID."""
        discussion = discussion_factory()

        response = authenticated_client.post(
            "/api/invites/discussion/send/",
            {"discussion_id": discussion.id, "invitee_user_id": 999999},
        )

        assert response.status_code == 404

    def test_accept_invite_invalid_id(self, authenticated_client):
        """Test accepting invite with invalid ID."""
        response = authenticated_client.post("/api/invites/999999/accept/")

        assert response.status_code == 404

    def test_accept_invite_already_accepted(
        self, authenticated_client, user_factory, discussion_factory
    ):
        """Test accepting already accepted invite."""
        inviter = user_factory()
        discussion = discussion_factory()

        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )

        invite = Invite.objects.create(
            inviter=inviter,
            invitee=authenticated_client.user,
            discussion=discussion,
            invite_type="discussion",
            status="accepted",
        )

        response = authenticated_client.post(f"/api/invites/{invite.id}/accept/")

        assert response.status_code == 400

    def test_decline_invite_invalid_id(self, authenticated_client):
        """Test declining invite with invalid ID."""
        response = authenticated_client.post("/api/invites/999999/decline/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestJoinRequestAPIErrors:
    """Test error handling in join request endpoints."""

    def test_create_join_request_invalid_discussion(self, authenticated_client):
        """Test creating join request for non-existent discussion."""
        response = authenticated_client.post(
            "/api/discussions/999999/join-request/", {"message": "Please let me join"}
        )

        assert response.status_code == 404

    def test_create_join_request_already_participant(
        self, authenticated_client, discussion_factory
    ):
        """Test creating join request when already a participant."""
        discussion = discussion_factory()

        DiscussionParticipant.objects.create(
            discussion=discussion, user=authenticated_client.user, role="active"
        )

        response = authenticated_client.post(
            f"/api/discussions/{discussion.id}/join-request/",
            {"message": "Let me join"},
        )

        assert response.status_code == 400

    def test_get_join_requests_not_participant(
        self, authenticated_client, discussion_factory
    ):
        """Test viewing join requests when not a participant."""
        discussion = discussion_factory()

        response = authenticated_client.get(
            f"/api/discussions/{discussion.id}/join-requests/"
        )

        assert response.status_code == 403

    def test_approve_join_request_invalid_id(
        self, authenticated_client, discussion_factory
    ):
        """Test approving non-existent join request."""
        response = authenticated_client.post(f"/api/join-requests/999999/approve/")

        assert response.status_code == 404

    def test_approve_join_request_not_participant(
        self, authenticated_client, discussion_factory, user_factory
    ):
        """Test approving join request when not a participant."""
        requester = user_factory()
        approver = user_factory()
        discussion = discussion_factory(initiator=approver)
        # Approver is the initiator with role="initiator" from factory

        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=approver,
            status="pending",
        )

        # authenticated_client's user tries to approve (but is NOT a participant)
        response = authenticated_client.post(
            f"/api/join-requests/{join_request.id}/approve/"
        )

        # Responds with 400 because the authenticated user can only approve their own assigned requests
        assert response.status_code == 400

    def test_decline_join_request_invalid_id(
        self, authenticated_client, discussion_factory
    ):
        """Test declining non-existent join request."""
        response = authenticated_client.post(f"/api/join-requests/999999/decline/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestOnboardingAPIErrors:
    """Test error handling in onboarding endpoints."""

    def test_complete_tutorial_already_complete(self, authenticated_client):
        """Test completing tutorial when already completed."""
        # First completion
        authenticated_client.post("/api/onboarding/tutorial/complete/")

        # Second attempt
        response = authenticated_client.post("/api/onboarding/tutorial/complete/")

        assert response.status_code == 200  # Idempotent


@pytest.mark.django_db
class TestValidationErrors:
    """Test field validation errors."""

    def test_register_with_taken_username(self, api_client, user_factory):
        """Test registration with username that already exists."""
        existing_user = user_factory(username="taken")

        import uuid

        verification_id = str(uuid.uuid4())
        code = "123456"
        phone = "+12025552222"

        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"

        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)

        response = api_client.post(
            "/api/auth/register/verify/",
            {"verification_id": verification_id, "code": code, "username": "taken"},
        )

        assert response.status_code == 400

    def test_register_with_short_username(self, api_client):
        """Test registration with username too short."""
        import uuid

        verification_id = str(uuid.uuid4())
        code = "123456"
        phone = "+12025553333"

        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"

        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)

        response = api_client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": verification_id,
                "code": code,
                "username": "ab",  # Too short (min 3)
            },
        )

        assert response.status_code == 400

    def test_discussion_invite_with_string_ids(self, authenticated_client):
        """Test sending discussion invite with invalid ID types."""
        response = authenticated_client.post(
            "/api/invites/discussion/send/",
            {"discussion_id": "not-an-int", "invitee_user_id": "also-not-an-int"},
        )

        assert response.status_code == 400
