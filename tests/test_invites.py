"""
Tests for invite system.

Tests platform and discussion invite creation, consumption, earning, and tracking.
"""

import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from core.models import (
    User,
    Invite,
    Discussion,
    DiscussionParticipant,
    PlatformConfig,
    Response,
)
from core.services.invite_service import InviteService


@pytest.mark.django_db
class TestInviteService:
    """Test invite service business logic."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_can_send_invite_insufficient_responses(self, user_factory):
        """Test user cannot send invite without enough responses."""
        user = user_factory()
        user.platform_invites_banked = 1
        user.save()

        # User has no responses
        can_send, reason = InviteService.can_send_invite(user, "platform")

        assert can_send is False
        assert "responses" in reason.lower()

    def test_can_send_invite_no_banked(self, user_factory, response_factory):
        """Test user cannot send invite without banked invites."""
        user = user_factory()
        user.platform_invites_banked = 0
        user.save()

        # Add enough responses
        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=user)

        can_send, reason = InviteService.can_send_invite(user, "platform")

        assert can_send is False
        assert "no platform invites available" in reason.lower()

    def test_can_send_invite_success(self, user_factory, response_factory):
        """Test user can send invite with sufficient requirements."""
        user = user_factory()
        user.platform_invites_banked = 1
        user.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=user)

        can_send, reason = InviteService.can_send_invite(user, "platform")

        assert can_send is True
        assert reason == ""

    def test_send_platform_invite(self, user_factory, response_factory):
        """Test platform invite creation."""
        user = user_factory()
        user.platform_invites_banked = 1
        user.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=user)

        invite, invite_code = InviteService.send_platform_invite(user)

        assert invite.inviter == user
        assert invite.invite_type == "platform"
        assert invite.status == "sent"
        assert len(invite_code) == 8

        # Check code is stored in invite model
        assert invite.code == invite_code
        assert invite.code is not None

    def test_send_platform_invite_consumption_sent(
        self, user_factory, response_factory
    ):
        """Test invite consumption on send (when configured)."""
        config = PlatformConfig.objects.get(pk=1)
        config.invite_consumption_trigger = "sent"
        config.save()

        user = user_factory()
        user.platform_invites_banked = 1
        user.platform_invites_used = 0
        user.save()

        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=user)

        initial_banked = user.platform_invites_banked

        invite, invite_code = InviteService.send_platform_invite(user)

        user.refresh_from_db()
        assert user.platform_invites_banked == initial_banked - 1
        assert user.platform_invites_used == 1

    def test_send_discussion_invite(
        self, user_factory, discussion_factory, response_factory
    ):
        """Test discussion invite creation."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        # Make inviter an active participant
        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )

        # Give inviter banked invites and responses
        inviter.discussion_invites_banked = 1
        inviter.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter)

        with patch("core.tasks.send_invite_notification.delay"):
            invite = InviteService.send_discussion_invite(inviter, discussion, invitee)

        assert invite.inviter == inviter
        assert invite.invitee == invitee
        assert invite.discussion == discussion
        assert invite.invite_type == "discussion"
        assert invite.status == "sent"

    def test_send_discussion_invite_not_participant(
        self, user_factory, discussion_factory
    ):
        """Test cannot send invite if not participant."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        inviter.discussion_invites_banked = 1
        inviter.save()

        with pytest.raises(ValidationError) as exc_info:
            InviteService.send_discussion_invite(inviter, discussion, invitee)

        assert "active participants" in str(exc_info.value).lower()

    def test_send_discussion_invite_already_participant(
        self, user_factory, discussion_factory, response_factory
    ):
        """Test cannot invite user who is already participant."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=invitee, role="active"
        )

        inviter.discussion_invites_banked = 1
        inviter.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter)

        with pytest.raises(ValidationError) as exc_info:
            InviteService.send_discussion_invite(inviter, discussion, invitee)

        assert "already a participant" in str(exc_info.value).lower()

    def test_accept_platform_invite(self, user_factory, response_factory):
        """Test accepting platform invite."""
        inviter = user_factory()
        inviter.platform_invites_banked = 1
        inviter.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter)

        invite, invite_code = InviteService.send_platform_invite(inviter)

        # Create new user
        new_user = User.objects.create_user(
            username="newuser", phone_number="+19998887777"
        )

        InviteService.accept_invite(invite, new_user)

        invite.refresh_from_db()
        assert invite.status == "accepted"
        assert invite.invitee == new_user

        # Check new user got starting invites
        new_user.refresh_from_db()
        assert new_user.platform_invites_banked == config.new_user_platform_invites
        assert new_user.discussion_invites_banked == config.new_user_discussion_invites

    def test_accept_invite_consumption_accepted(self, user_factory, response_factory):
        """Test invite consumed on accept (when configured)."""
        config = PlatformConfig.objects.get(pk=1)
        config.invite_consumption_trigger = "accepted"
        config.save()

        inviter = user_factory()
        inviter.platform_invites_banked = 1
        inviter.platform_invites_used = 0
        inviter.save()

        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter)

        invite, invite_code = InviteService.send_platform_invite(inviter)

        # Banked should not change on send
        inviter.refresh_from_db()
        initial_banked = inviter.platform_invites_banked

        new_user = User.objects.create_user(
            username="newuser", phone_number="+19998887777"
        )
        InviteService.accept_invite(invite, new_user)

        # Should be consumed on accept
        inviter.refresh_from_db()
        assert inviter.platform_invites_banked == initial_banked - 1
        assert inviter.platform_invites_used == 1

    def test_decline_invite(self, user_factory, discussion_factory, response_factory):
        """Test declining invite."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        DiscussionParticipant.objects.create(
            discussion=discussion, user=inviter, role="active"
        )

        inviter.discussion_invites_banked = 1
        inviter.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=inviter)

        with patch("core.tasks.send_invite_notification.delay"):
            invite = InviteService.send_discussion_invite(inviter, discussion, invitee)

        InviteService.decline_invite(invite, invitee)

        invite.refresh_from_db()
        assert invite.status == "declined"

    def test_earn_invite_from_response(self, user_factory, response_factory):
        """Test earning invites from responses."""
        user = user_factory()
        config = PlatformConfig.objects.get(pk=1)

        # Create enough responses to earn 2 platform invites
        num_responses = config.responses_per_platform_invite * 2
        for _ in range(num_responses):
            response_factory(user=user)

        result = InviteService.earn_invite_from_response(user)

        user.refresh_from_db()
        assert user.platform_invites_acquired == 2
        assert user.platform_invites_banked == 2

    def test_invite_formula_validation(self, user_factory):
        """Test invite formula: acquired = used + banked."""
        user = user_factory()
        user.platform_invites_acquired = 10
        user.platform_invites_used = 3
        user.platform_invites_banked = 7
        user.save()

        # Formula should balance
        assert user.platform_invites_acquired == (
            user.platform_invites_used + user.platform_invites_banked
        )

    def test_track_first_participation(self, user_factory, discussion_factory):
        """Test tracking first participation after invite."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        # Create and accept invite
        invite = Invite.objects.create(
            inviter=inviter,
            invitee=invitee,
            discussion=discussion,
            invite_type="discussion",
            status="accepted",
        )

        assert invite.first_participation_at is None

        InviteService.track_first_participation(invitee, discussion)

        invite.refresh_from_db()
        assert invite.first_participation_at is not None


@pytest.mark.django_db
class TestInviteAPI:
    """Test invite API endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_my_invites_endpoint(
        self, authenticated_client, user_factory, response_factory
    ):
        """Test getting user's invite stats."""
        user = authenticated_client.user
        user.platform_invites_acquired = 5
        user.platform_invites_used = 2
        user.platform_invites_banked = 3
        user.discussion_invites_acquired = 10
        user.discussion_invites_used = 7
        user.discussion_invites_banked = 3
        user.save()

        response = authenticated_client.get("/api/invites/me/")

        assert response.status_code == 200
        assert response.data["platform_invites"]["acquired"] == 5
        assert response.data["platform_invites"]["used"] == 2
        assert response.data["platform_invites"]["banked"] == 3
        assert response.data["discussion_invites"]["banked"] == 3

    def test_send_platform_invite_endpoint(
        self, authenticated_client, response_factory
    ):
        """Test sending platform invite via API."""
        user = authenticated_client.user
        user.platform_invites_banked = 1
        user.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=user)

        response = authenticated_client.post("/api/invites/platform/send/")

        assert response.status_code == 200
        assert "invite_code" in response.data
        assert "invite_url" in response.data
        assert len(response.data["invite_code"]) == 8

    def test_user_invite_metrics_public(self, api_client, user_factory):
        """Test public invite metrics endpoint."""
        user = user_factory()
        user.platform_invites_acquired = 10
        user.platform_invites_used = 3
        user.platform_invites_banked = 7
        user.save()

        response = api_client.get(f"/api/users/{user.id}/invite-metrics/")

        assert response.status_code == 200
        assert response.data["platform_invites"]["acquired"] == 10
        assert response.data["is_penalized"] is False
