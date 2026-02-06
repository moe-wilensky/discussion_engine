"""Tests for Celery tasks covering the simple/testable task paths."""

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from core.models import (
    User, Discussion, DiscussionParticipant, Round, Response,
    PlatformConfig, Invite, JoinRequest, NotificationLog,
)


class TestSendVerificationSMS(TestCase):
    """Tests for the send_verification_sms task."""

    def test_mock_mode(self):
        from core.tasks import send_verification_sms
        result = send_verification_sms("+15551234567", "123456")
        assert "Mock SMS sent" in result

    def test_mock_mode_masks_phone(self):
        from core.tasks import send_verification_sms
        result = send_verification_sms("+15551234567", "123456")
        assert "4567" in result
        assert "+1555" not in result


class TestInviteNotificationTask(TestCase):
    """Tests for the send_invite_notification task."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user1 = User.objects.create_user(
            username="user1", phone_number="+15551111111"
        )
        self.user2 = User.objects.create_user(
            username="user2", phone_number="+15552222222"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Details",
            initiator=self.user1,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )

    def test_existing_invite(self):
        from core.tasks import send_invite_notification
        invite = Invite.objects.create(
            inviter=self.user1, invitee=self.user2,
            invite_type="discussion", discussion=self.discussion,
        )
        result = send_invite_notification(str(invite.id))
        assert "Notification sent" in result

    def test_nonexistent_invite(self):
        from core.tasks import send_invite_notification
        result = send_invite_notification(str(999999))
        assert "not found" in result


class TestJoinRequestNotificationTasks(TestCase):
    """Tests for join request notification tasks."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user1 = User.objects.create_user(
            username="requester", phone_number="+15551111111"
        )
        self.user2 = User.objects.create_user(
            username="approver", phone_number="+15552222222"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test", topic_details="Details",
            initiator=self.user2,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.join_request = JoinRequest.objects.create(
            requester=self.user1, discussion=self.discussion,
            approver=self.user2, status="pending",
        )

    def test_send_join_request_notification_found(self):
        from core.tasks import send_join_request_notification
        result = send_join_request_notification(str(self.join_request.id))
        assert "Notification sent" in result

    def test_send_join_request_notification_not_found(self):
        from core.tasks import send_join_request_notification
        result = send_join_request_notification(str(999999))
        assert "not found" in result

    def test_send_approved_notification_found(self):
        from core.tasks import send_join_request_approved_notification
        result = send_join_request_approved_notification(str(self.join_request.id))
        assert "Approval notification sent" in result

    def test_send_approved_notification_not_found(self):
        from core.tasks import send_join_request_approved_notification
        result = send_join_request_approved_notification(str(999999))
        assert "not found" in result

    def test_send_declined_notification_found(self):
        from core.tasks import send_join_request_declined_notification
        result = send_join_request_declined_notification(str(self.join_request.id))
        assert "Decline notification sent" in result

    def test_send_declined_notification_not_found(self):
        from core.tasks import send_join_request_declined_notification
        result = send_join_request_declined_notification(str(999999))
        assert "not found" in result


class TestCleanupTasks(TestCase):
    """Tests for cleanup and maintenance tasks."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111"
        )

    def test_cleanup_expired_invites(self):
        from core.tasks import cleanup_expired_invites
        user2 = User.objects.create_user(
            username="user2", phone_number="+15552222222"
        )
        # Create an old invite
        invite = Invite.objects.create(
            inviter=self.user, invitee=user2,
            invite_type="platform", status="sent",
        )
        # Backdate it
        Invite.objects.filter(id=invite.id).update(
            sent_at=timezone.now() - timedelta(days=31)
        )
        result = cleanup_expired_invites()
        assert "Expired 1 invites" in result
        invite.refresh_from_db()
        assert invite.status == "expired"

    def test_cleanup_expired_verification_codes(self):
        from core.tasks import cleanup_expired_verification_codes
        result = cleanup_expired_verification_codes()
        assert "Cleanup complete" in result

    def test_send_daily_digest(self):
        from core.tasks import send_daily_digest
        result = send_daily_digest()
        assert "0 daily digests" in result


class TestWarningTasks(TestCase):
    """Tests for warning/notification tasks."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test", topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )

    def test_send_single_response_warning_with_one_response(self):
        from core.tasks import send_single_response_warning
        Response.objects.create(
            round=self.round, user=self.user, content="Only response"
        )
        result = send_single_response_warning(self.discussion.id, 1)
        assert "Single response warning" in result

    def test_send_single_response_warning_round_not_found(self):
        from core.tasks import send_single_response_warning
        result = send_single_response_warning(self.discussion.id, 999)
        assert "not found" in result

    def test_send_mrp_warning_round_not_found(self):
        from core.tasks import send_mrp_warning
        result = send_mrp_warning(self.discussion.id, 999, 25)
        assert "not found" in result

    def test_send_voting_window_closing_warning(self):
        from core.tasks import send_voting_window_closing_warning
        result = send_voting_window_closing_warning(self.round.id, 10)
        assert "Sent warning" in result

    def test_send_voting_window_closing_warning_not_found(self):
        from core.tasks import send_voting_window_closing_warning
        result = send_voting_window_closing_warning(999999, 10)
        assert "not found" in result

    def test_send_removal_warning(self):
        from core.tasks import send_removal_warning
        result = send_removal_warning(self.user.id, self.discussion.id, 2, 50.0)
        assert "Sent removal warning" in result

    def test_send_removal_warning_not_found(self):
        from core.tasks import send_removal_warning
        result = send_removal_warning(999999, 999999, 2, 50.0)
        assert "not found" in result

    def test_send_permanent_observer_notification(self):
        from core.tasks import send_permanent_observer_notification
        result = send_permanent_observer_notification(
            self.user.id, self.discussion.id, "vote_based_removal"
        )
        assert "Sent permanent observer notification" in result

    def test_send_permanent_observer_notification_not_found(self):
        from core.tasks import send_permanent_observer_notification
        result = send_permanent_observer_notification(999999, 999999, "test")
        assert "not found" in result

    def test_broadcast_new_response_not_found(self):
        from core.tasks import broadcast_new_response
        result = broadcast_new_response(self.discussion.id, 999999)
        assert "not found" in result


class TestBroadcastMRPTimers(TestCase):
    """Tests for the broadcast_mrp_timers task."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test", topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )

    @patch("core.tasks.get_channel_layer", return_value=None)
    def test_no_channel_layer(self, mock_layer):
        from core.tasks import broadcast_mrp_timers
        result = broadcast_mrp_timers()
        assert "not configured" in result


class TestAutoArchiveAbandonedDiscussions(TestCase):
    """Tests for auto-archiving abandoned discussions."""

    def setUp(self):
        config = PlatformConfig.load()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Old Discussion", topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )

    def test_archives_abandoned_discussions(self):
        from core.tasks import auto_archive_abandoned_discussions
        # Backdate the discussion's created_at
        Discussion.objects.filter(id=self.discussion.id).update(
            created_at=timezone.now() - timedelta(days=61)
        )
        result = auto_archive_abandoned_discussions()
        assert "1" in result
        self.discussion.refresh_from_db()
        assert self.discussion.status == "archived"

    def test_does_not_archive_active_discussions(self):
        from core.tasks import auto_archive_abandoned_discussions
        result = auto_archive_abandoned_discussions()
        self.discussion.refresh_from_db()
        assert self.discussion.status == "active"
