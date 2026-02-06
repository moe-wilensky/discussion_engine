"""
Comprehensive tests for moderation and notification systems.

Tests mutual removal, escalation rules, notification preferences,
and integration with existing systems.
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from core.models import (
    User,
    Discussion,
    Round,
    DiscussionParticipant,
    ModerationAction,
    NotificationLog,
    NotificationPreference,
    PlatformConfig,
    Response,
)
from core.services.mutual_removal_service import MutualRemovalService
from core.services.notification_service import NotificationService


@pytest.mark.django_db
class TestMutualRemoval:
    """Tests for mutual removal system"""

    def test_mutual_removal_basic(
        self, user_factory, discussion_factory, round_factory
    ):
        """Test basic mutual removal"""
        user_a = user_factory(username="user_a")
        user_b = user_factory(username="user_b")
        discussion = discussion_factory(initiator=user_a)
        round_obj = round_factory(
            discussion=discussion, round_number=1, status="in_progress"
        )

        # Get/create participants (initiator already exists from factory)
        participant_a = DiscussionParticipant.objects.get(
            discussion=discussion, user=user_a
        )
        participant_b = DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )

        # Both users must post in current round before using kamikaze
        Response.objects.create(
            user=user_a,
            round=round_obj,
            content="Response from user A"
        )
        Response.objects.create(
            user=user_b,
            round=round_obj,
            content="Response from user B"
        )

        # Execute mutual removal
        moderation_action = MutualRemovalService.initiate_removal(
            initiator=user_a,
            target=user_b,
            discussion=discussion,
            current_round=round_obj,
        )

        # Verify both moved to temporary observer
        participant_a.refresh_from_db()
        participant_b.refresh_from_db()

        assert participant_a.role == "temporary_observer"
        assert participant_b.role == "temporary_observer"
        assert participant_a.observer_reason == "mutual_removal"
        assert participant_b.observer_reason == "mutual_removal"
        assert participant_a.removal_count == 1
        assert participant_b.times_removed == 1

        # Verify ModerationAction created
        assert moderation_action.action_type == "mutual_removal"
        assert moderation_action.initiator == user_a
        assert moderation_action.target == user_b

    def test_mutual_removal_escalation_target(
        self, user_factory, discussion_factory, round_factory
    ):
        """Test target becomes permanent after 3 removals"""
        user_a = user_factory(username="user_a")
        user_b = user_factory(
            username="user_b", platform_invites_acquired=5, platform_invites_banked=3
        )
        user_c = user_factory(username="user_c")
        user_d = user_factory(username="user_d")

        discussion = discussion_factory(initiator=user_a)
        round_obj = round_factory(
            discussion=discussion, round_number=1, status="in_progress"
        )

        # Create participants (user_a already exists as initiator from factory)
        for user in [user_b, user_c, user_d]:
            DiscussionParticipant.objects.create(
                discussion=discussion, user=user, role="active"
            )

        # Both users must post before using kamikaze
        Response.objects.create(
            user=user_a, round=round_obj, content="Response A"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B"
        )

        # First removal
        MutualRemovalService.initiate_removal(user_a, user_b, discussion, round_obj)
        participant_b = DiscussionParticipant.objects.get(
            discussion=discussion, user=user_b
        )
        assert participant_b.times_removed == 1

        # Rejoin
        participant_b.role = "active"
        participant_b.save()

        # Create responses for second kamikaze
        Response.objects.create(
            user=user_c, round=round_obj, content="Response C"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B2"
        )

        # Second removal
        MutualRemovalService.initiate_removal(user_c, user_b, discussion, round_obj)
        participant_b.refresh_from_db()
        assert participant_b.times_removed == 2

        # Rejoin
        participant_b.role = "active"
        participant_b.save()

        # Create responses for third kamikaze
        Response.objects.create(
            user=user_d, round=round_obj, content="Response D"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B3"
        )

        # Third removal - becomes permanent
        MutualRemovalService.initiate_removal(user_d, user_b, discussion, round_obj)
        participant_b.refresh_from_db()
        user_b.refresh_from_db()

        assert participant_b.times_removed == 3
        assert participant_b.role == "permanent_observer"
        assert user_b.platform_invites_acquired == 0
        assert user_b.platform_invites_banked == 0

    def test_cannot_remove_twice(self, user_factory, discussion_factory, round_factory):
        """Test duplicate removal prevention"""
        user_a = user_factory(username="user_a")
        user_b = user_factory(username="user_b")
        discussion = discussion_factory(initiator=user_a)
        round_obj = round_factory(
            discussion=discussion, round_number=1, status="in_progress"
        )

        # Get initiator (already exists) and create user_b
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )

        # Both users must post before using kamikaze
        Response.objects.create(
            user=user_a, round=round_obj, content="Response A"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B"
        )

        # First removal
        MutualRemovalService.initiate_removal(user_a, user_b, discussion, round_obj)

        # Make both active again
        for user in [user_a, user_b]:
            participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=user
            )
            participant.role = "active"
            participant.save()

        # Second attempt should fail
        can_remove, reason = MutualRemovalService.can_initiate_removal(
            user_a, user_b, discussion
        )
        assert not can_remove
        assert "already removed" in reason.lower()


@pytest.mark.django_db
class TestNotifications:
    """Tests for notification system"""

    def test_notification_preferences_creation(self, user_factory):
        """Test default preferences"""
        user = user_factory(username="test_user")
        NotificationService.create_notification_preferences(user)

        # Check critical notifications
        for notification_type in NotificationService.CRITICAL_NOTIFICATIONS:
            pref = NotificationPreference.objects.get(
                user=user, notification_type=notification_type
            )
            assert pref.enabled
            assert pref.delivery_method["in_app"]

        # Check optional notifications
        for notification_type in NotificationService.OPTIONAL_NOTIFICATIONS:
            pref = NotificationPreference.objects.get(
                user=user, notification_type=notification_type
            )
            assert not pref.enabled

    def test_critical_notification_always_sent(self, user_factory):
        """Test critical notifications always sent"""
        user = user_factory(username="test_user")
        NotificationService.create_notification_preferences(user)

        NotificationService.send_notification(
            user=user,
            notification_type="mrp_expiring_soon",
            context={"discussion_headline": "Test", "time_remaining": "10m"},
            delivery_methods=["in_app"],
        )

        assert NotificationLog.objects.filter(
            user=user, notification_type="mrp_expiring_soon"
        ).exists()

    def test_optional_notification_respects_preferences(self, user_factory):
        """Test optional notifications respect preferences"""
        user = user_factory(username="test_user")
        NotificationService.create_notification_preferences(user)

        # Disabled by default - should not be sent
        NotificationService.send_notification(
            user=user,
            notification_type="new_response_posted",
            context={"discussion_headline": "Test"},
            delivery_methods=["in_app"],
        )

        assert not NotificationLog.objects.filter(
            user=user, notification_type="new_response_posted"
        ).exists()

        # Enable the notification
        pref = NotificationPreference.objects.get(
            user=user, notification_type="new_response_posted"
        )
        pref.enabled = True
        pref.save()

        # Now it should be sent
        NotificationService.send_notification(
            user=user,
            notification_type="new_response_posted",
            context={"discussion_headline": "Test"},
            delivery_methods=["in_app"],
        )

        assert NotificationLog.objects.filter(
            user=user, notification_type="new_response_posted"
        ).exists()

    def test_mutual_removal_notifications(
        self, user_factory, discussion_factory, round_factory
    ):
        """Test mutual removal notifications"""
        user_a = user_factory(username="user_a")
        user_b = user_factory(username="user_b")
        discussion = discussion_factory(initiator=user_a)
        round_obj = round_factory(
            discussion=discussion, round_number=1, status="in_progress"
        )

        # Get initiator (already exists) and create user_b
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )

        for user in [user_a, user_b]:
            NotificationService.create_notification_preferences(user)

        # Both users must post before using kamikaze
        Response.objects.create(
            user=user_a, round=round_obj, content="Response A"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B"
        )

        # Execute mutual removal
        MutualRemovalService.initiate_removal(user_a, user_b, discussion, round_obj)

        # Both should have notifications
        assert NotificationLog.objects.filter(
            user=user_a, notification_type="mutual_removal_initiated"
        ).exists()
        assert NotificationLog.objects.filter(
            user=user_b, notification_type="mutual_removal_initiated"
        ).exists()


@pytest.mark.django_db
class TestIntegration:
    """Integration tests"""

    def test_moderation_notification_integration(
        self, user_factory, discussion_factory, round_factory
    ):
        """End-to-end moderation and notification test"""
        user_a = user_factory(username="user_a")
        user_b = user_factory(username="user_b")
        user_c = user_factory(username="user_c")
        user_d = user_factory(username="user_d")

        discussion = discussion_factory(initiator=user_a)
        round_obj = round_factory(
            discussion=discussion, round_number=1, status="in_progress"
        )

        # Create participants (user_a already exists as initiator from factory)
        for user in [user_b, user_c, user_d]:
            DiscussionParticipant.objects.create(
                discussion=discussion, user=user, role="active"
            )

        # Create notification preferences for all users
        for user in [user_a, user_b, user_c, user_d]:
            NotificationService.create_notification_preferences(user)

        # Both users must post before using kamikaze
        Response.objects.create(
            user=user_a, round=round_obj, content="Response A"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B"
        )

        # User A removes User B
        MutualRemovalService.initiate_removal(user_a, user_b, discussion, round_obj)

        # Check notifications
        assert NotificationLog.objects.filter(
            user=user_a, notification_type="mutual_removal_initiated"
        ).exists()
        assert NotificationLog.objects.filter(
            user=user_b, notification_type="mutual_removal_initiated"
        ).exists()

        # Check observer status
        participant_a = DiscussionParticipant.objects.get(
            discussion=discussion, user=user_a
        )
        participant_b = DiscussionParticipant.objects.get(
            discussion=discussion, user=user_b
        )
        assert participant_a.role == "temporary_observer"
        assert participant_b.role == "temporary_observer"

        # Rejoin both
        participant_a.role = "active"
        participant_b.role = "active"
        participant_a.save()
        participant_b.save()

        # Create responses for second kamikaze
        Response.objects.create(
            user=user_c, round=round_obj, content="Response C"
        )
        Response.objects.create(
            user=user_b, round=round_obj, content="Response B2"
        )

        # User C removes User B (2nd time)
        MutualRemovalService.initiate_removal(user_c, user_b, discussion, round_obj)
        participant_b.refresh_from_db()
        assert participant_b.times_removed == 2

        # Escalation warning should be sent
        assert NotificationLog.objects.filter(
            user=user_b, notification_type="mutual_removal_escalation_warning"
        ).exists()
