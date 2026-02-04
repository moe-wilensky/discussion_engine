"""
Tests for discussion initiator permissions and role-based access.

Verifies that users with role="initiator" have proper permissions to:
- Send discussion invites
- Be assigned as join request approvers
- Participate in discussions
"""

import pytest
from unittest.mock import patch
from django.core.exceptions import ValidationError

from core.models import (
    User,
    Discussion,
    DiscussionParticipant,
    PlatformConfig,
    Invite,
    JoinRequest,
)
from core.services.invite_service import InviteService
from core.services.join_request import JoinRequestService


@pytest.mark.django_db
class TestInitiatorInvitePermissions:
    """Test that discussion initiators can send invites."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_initiator_can_send_discussion_invite(
        self, user_factory, discussion_factory, response_factory
    ):
        """Test that initiator (role='initiator') can send discussion invites."""
        initiator = user_factory()
        invitee = user_factory()
        discussion = discussion_factory(initiator=initiator)
        # Initiator has DiscussionParticipant with role="initiator" from factory

        # Give initiator banked invites and responses
        initiator.discussion_invites_banked = 1
        initiator.save()

        config = PlatformConfig.objects.get(pk=1)
        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=initiator, discussion=discussion)

        # Initiator should be able to send invites to their own discussion
        with patch("core.tasks.send_invite_notification.delay"):
            invite = InviteService.send_discussion_invite(initiator, discussion, invitee)

        assert invite.inviter == initiator
        assert invite.invitee == invitee
        assert invite.discussion == discussion
        assert invite.invite_type == "discussion"
        assert invite.status == "sent"

        # Verify initiator still has role="initiator"
        initiator_participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=initiator
        )
        assert initiator_participant.role == "initiator"

    def test_initiator_counts_toward_participant_cap(
        self, user_factory, discussion_factory, response_factory
    ):
        """Test that initiators are counted in participant capacity checks."""
        config = PlatformConfig.objects.get(pk=1)
        initiator = user_factory()
        discussion = discussion_factory(initiator=initiator)
        # Now discussion has 1 participant (the initiator)

        initiator.discussion_invites_banked = 10
        initiator.save()

        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=initiator, discussion=discussion)

        # Fill discussion to capacity (minus 1 for initiator)
        for i in range(config.max_discussion_participants - 1):
            user = user_factory()
            DiscussionParticipant.objects.create(
                discussion=discussion, user=user, role="active"
            )

        # Discussion should now be at capacity
        final_invitee = user_factory()
        with pytest.raises(ValidationError) as exc_info:
            InviteService.send_discussion_invite(initiator, discussion, final_invitee)

        assert "maximum capacity" in str(exc_info.value).lower()


@pytest.mark.django_db
class TestInitiatorJoinRequestPermissions:
    """Test that discussion initiators can handle join requests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_initiator_assigned_as_join_request_approver(
        self, user_factory, discussion_factory
    ):
        """Test that initiator is found and assigned as approver for join requests."""
        initiator = user_factory()
        requester = user_factory()
        discussion = discussion_factory(initiator=initiator)
        # Initiator has DiscussionParticipant with role="initiator" from factory

        with patch("core.tasks.send_join_request_notification.delay"):
            request = JoinRequestService.create_request(
                discussion, requester, "I'd like to join"
            )

        assert request.approver == initiator
        assert request.requester == requester
        assert request.discussion == discussion
        assert request.status == "pending"

        # Verify initiator still has role="initiator"
        initiator_participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=initiator
        )
        assert initiator_participant.role == "initiator"

    def test_initiator_can_approve_join_request(
        self, user_factory, discussion_factory
    ):
        """Test that initiator can approve join requests."""
        initiator = user_factory()
        requester = user_factory()
        discussion = discussion_factory(initiator=initiator)

        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator,
            status="pending",
        )

        with patch("core.tasks.send_join_request_approved_notification.delay"):
            participant = JoinRequestService.approve_request(request, initiator)

        assert participant.user == requester
        assert participant.discussion == discussion
        assert participant.role == "active"

        request.refresh_from_db()
        assert request.status == "approved"

    def test_initiator_can_decline_join_request(
        self, user_factory, discussion_factory
    ):
        """Test that initiator can decline join requests."""
        initiator = user_factory()
        requester = user_factory()
        discussion = discussion_factory(initiator=initiator)

        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator,
            status="pending",
        )

        with patch("core.tasks.send_join_request_declined_notification.delay"):
            JoinRequestService.decline_request(
                request, initiator, "Thanks but we're full"
            )

        request.refresh_from_db()
        assert request.status == "declined"

    def test_initiator_counted_in_participant_cap_for_join_requests(
        self, user_factory, discussion_factory
    ):
        """Test that initiators are counted when checking discussion capacity for join requests."""
        config = PlatformConfig.objects.get(pk=1)
        initiator = user_factory()
        discussion = discussion_factory(initiator=initiator)
        # Now discussion has 1 participant (the initiator)

        # Fill discussion to capacity (minus 1 for initiator)
        for i in range(config.max_discussion_participants - 1):
            user = user_factory()
            DiscussionParticipant.objects.create(
                discussion=discussion, user=user, role="active"
            )

        # Discussion should now be at capacity
        requester = user_factory()
        with pytest.raises(ValidationError) as exc_info:
            JoinRequestService.create_request(discussion, requester)

        assert "maximum capacity" in str(exc_info.value).lower()


@pytest.mark.django_db
class TestInitiatorAndActiveParticipantEquality:
    """Test that initiators and active participants are treated equally for permissions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_both_roles_can_send_invites(
        self, user_factory, discussion_factory, response_factory
    ):
        """Test that both role='initiator' and role='active' can send invites."""
        config = PlatformConfig.objects.get(pk=1)

        # Test with initiator
        initiator = user_factory()
        discussion1 = discussion_factory(initiator=initiator)
        invitee1 = user_factory()

        initiator.discussion_invites_banked = 1
        initiator.save()

        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=initiator, discussion=discussion1)

        with patch("core.tasks.send_invite_notification.delay"):
            invite1 = InviteService.send_discussion_invite(
                initiator, discussion1, invitee1
            )
        assert invite1 is not None

        # Test with active participant
        discussion2 = discussion_factory()
        active_user = user_factory()
        DiscussionParticipant.objects.create(
            discussion=discussion2, user=active_user, role="active"
        )
        invitee2 = user_factory()

        active_user.discussion_invites_banked = 1
        active_user.save()

        for _ in range(config.responses_to_unlock_invites):
            response_factory(user=active_user, discussion=discussion2)

        with patch("core.tasks.send_invite_notification.delay"):
            invite2 = InviteService.send_discussion_invite(
                active_user, discussion2, invitee2
            )
        assert invite2 is not None

    def test_both_roles_can_approve_join_requests(
        self, user_factory, discussion_factory
    ):
        """Test that both role='initiator' and role='active' can approve join requests."""
        # Test with initiator
        initiator = user_factory()
        discussion1 = discussion_factory(initiator=initiator)
        requester1 = user_factory()

        request1 = JoinRequest.objects.create(
            discussion=discussion1,
            requester=requester1,
            approver=initiator,
            status="pending",
        )

        with patch("core.tasks.send_join_request_approved_notification.delay"):
            participant1 = JoinRequestService.approve_request(request1, initiator)
        assert participant1 is not None

        # Test with active participant
        discussion2 = discussion_factory()
        active_user = user_factory()
        DiscussionParticipant.objects.create(
            discussion=discussion2, user=active_user, role="active"
        )
        requester2 = user_factory()

        request2 = JoinRequest.objects.create(
            discussion=discussion2,
            requester=requester2,
            approver=active_user,
            status="pending",
        )

        with patch("core.tasks.send_join_request_approved_notification.delay"):
            participant2 = JoinRequestService.approve_request(request2, active_user)
        assert participant2 is not None
