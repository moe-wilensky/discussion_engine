"""
Comprehensive integration tests for admin API endpoints.

Tests all admin-related endpoints including:
- Platform configuration management
- Platform analytics
- User analytics
- User flagging and moderation
- User banning/unbanning
- Phone verification
- Moderation queue management
"""

import pytest
from unittest.mock import patch
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    PlatformConfig,
    Discussion,
    DiscussionParticipant,
    Response,
    Round,
    Invite,
    AdminFlag,
    UserBan,
    ModerationAction,
)


@pytest.fixture
def admin_user(user_factory):
    """Create an admin user."""
    user = user_factory()
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def superadmin_user(user_factory):
    """Create a superadmin user."""
    user = user_factory()
    user.is_staff = True
    user.is_superuser = True
    user.save()
    return user


@pytest.fixture
def admin_client(admin_user):
    """Provide authenticated admin API client."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    client.user = admin_user

    return client


@pytest.fixture
def superadmin_client(superadmin_user):
    """Provide authenticated superadmin API client."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    refresh = RefreshToken.for_user(superadmin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    client.user = superadmin_user

    return client


@pytest.mark.django_db
class TestPlatformConfig:
    """Test platform configuration endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_platform_config(self, admin_client):
        """Test retrieving platform configuration."""
        response = admin_client.get("/api/admin/platform-config/")

        assert response.status_code == 200
        assert "config" in response.data
        assert "last_updated" in response.data

        # Check expected config fields
        config = response.data["config"]
        assert "new_user_platform_invites" in config
        assert "new_user_discussion_invites" in config
        assert "responses_to_unlock_invites" in config
        assert "max_discussion_participants" in config
        assert "n_responses_before_mrp" in config

    def test_get_platform_config_requires_admin(self, authenticated_client):
        """Test that getting config requires admin permission."""
        response = authenticated_client.get("/api/admin/platform-config/")

        assert response.status_code == 403

    def test_update_platform_config(self, superadmin_client):
        """Test updating platform configuration."""
        response = superadmin_client.patch(
            "/api/admin/platform-config/update/",
            {
                "new_user_platform_invites": 10,
                "new_user_discussion_invites": 50,
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["updated"] is True
        assert "changes" in response.data

        # Check changes are reflected
        config = response.data["config"]
        assert config["new_user_platform_invites"] == 10
        assert config["new_user_discussion_invites"] == 50

        # Check changes list
        changes = response.data["changes"]
        assert len(changes) == 2

    def test_update_platform_config_requires_superadmin(self, admin_client):
        """Test that updating config requires superadmin permission."""
        response = admin_client.patch(
            "/api/admin/platform-config/update/",
            {"new_user_platform_invites": 10},
            format="json",
        )

        assert response.status_code == 403

    def test_update_platform_config_invalid_field(self, superadmin_client):
        """Test updating with invalid field name."""
        response = superadmin_client.patch(
            "/api/admin/platform-config/update/",
            {"invalid_field": 123},
            format="json",
        )

        assert response.status_code == 400
        assert "Invalid field" in response.data["error"]

    def test_update_platform_config_invalid_value(self, superadmin_client):
        """Test updating with invalid value."""
        response = superadmin_client.patch(
            "/api/admin/platform-config/update/",
            {"new_user_platform_invites": -5},
            format="json",
        )

        assert response.status_code == 400
        assert "must be non-negative" in response.data["error"]

    def test_update_platform_config_invalid_type(self, superadmin_client):
        """Test updating with invalid value type."""
        response = superadmin_client.patch(
            "/api/admin/platform-config/update/",
            {"new_user_platform_invites": "not_a_number"},
            format="json",
        )

        assert response.status_code == 400

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_update_platform_config_notifies_admins(
        self, mock_notify, superadmin_client, admin_user
    ):
        """Test that config updates notify all admins."""
        response = superadmin_client.patch(
            "/api/admin/platform-config/update/",
            {"new_user_platform_invites": 15},
            format="json",
        )

        assert response.status_code == 200

        # Check notification was sent
        assert mock_notify.called


@pytest.mark.django_db
class TestPlatformAnalytics:
    """Test platform analytics endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_platform_analytics_empty(self, admin_client):
        """Test getting analytics with no data."""
        response = admin_client.get("/api/admin/analytics/")

        assert response.status_code == 200

        # Check structure
        assert "users" in response.data
        assert "discussions" in response.data
        assert "engagement" in response.data
        assert "moderation" in response.data
        assert "abuse" in response.data

        # Check user metrics
        users = response.data["users"]
        assert "total" in users
        assert "active_7_days" in users
        assert "active_30_days" in users
        assert "new_this_week" in users
        assert "banned" in users
        assert "flagged" in users

    def test_get_platform_analytics_with_data(
        self, admin_client, user_factory, discussion_factory, response_factory
    ):
        """Test getting analytics with actual data."""
        # Create users
        for i in range(5):
            user_factory()

        # Create discussions
        for i in range(3):
            discussion = discussion_factory()

            # Create responses
            for j in range(2):
                response_factory(discussion=discussion)

        response = admin_client.get("/api/admin/analytics/")

        assert response.status_code == 200

        # Check user counts (5 + 1 admin + factory-created users)
        assert response.data["users"]["total"] >= 5

        # Check discussion counts
        assert response.data["discussions"]["total"] >= 3

        # Check engagement metrics
        assert response.data["engagement"]["total_responses"] >= 6

    def test_get_platform_analytics_user_activity(
        self, admin_client, user_factory
    ):
        """Test analytics with users of different activity levels."""
        now = timezone.now()

        # Active user (logged in recently)
        active_user = user_factory()
        active_user.last_login = now - timedelta(days=2)
        active_user.save()

        # Inactive user (logged in long ago)
        inactive_user = user_factory()
        inactive_user.last_login = now - timedelta(days=45)
        inactive_user.save()

        # New user (created this week)
        new_user = user_factory()
        new_user.created_at = now - timedelta(days=3)
        new_user.save()

        response = admin_client.get("/api/admin/analytics/")

        assert response.status_code == 200

        # Check activity metrics
        users = response.data["users"]
        assert users["active_7_days"] >= 1
        assert users["new_this_week"] >= 1

    def test_get_platform_analytics_moderation_metrics(
        self, admin_client, user_factory, discussion_factory
    ):
        """Test analytics with moderation data."""
        user1 = user_factory()
        user2 = user_factory()
        discussion = discussion_factory()

        # Create a round for the discussion
        from core.models import Round
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="completed"
        )

        # Create moderation action
        ModerationAction.objects.create(
            discussion=discussion,
            initiator=user1,
            target=user2,
            action_type="mutual_removal",
            round_occurred=round_obj,
            is_permanent=True,
        )

        # Create participant as permanent observer
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user2, role="permanent_observer"
        )

        response = admin_client.get("/api/admin/analytics/")

        assert response.status_code == 200

        # Check moderation metrics
        moderation = response.data["moderation"]
        assert moderation["mutual_removals"] >= 1
        assert moderation["permanent_observers"] >= 1

    def test_get_platform_analytics_requires_admin(self, authenticated_client):
        """Test that analytics require admin permission."""
        response = authenticated_client.get("/api/admin/analytics/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestUserAnalytics:
    """Test user analytics endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_user_analytics(
        self, admin_client, user_factory, discussion_factory, response_factory
    ):
        """Test getting analytics for a specific user."""
        target_user = user_factory()

        # Create participation data
        discussion = discussion_factory()
        DiscussionParticipant.objects.create(
            discussion=discussion, user=target_user, role="active"
        )
        response_factory(user=target_user, discussion=discussion)
        response_factory(user=target_user, discussion=discussion)

        response = admin_client.get(f"/api/admin/users/{target_user.id}/analytics/")

        assert response.status_code == 200

        # Check structure
        assert "user" in response.data
        assert "participation" in response.data
        assert "moderation" in response.data
        assert "invitations" in response.data
        assert "abuse_score" in response.data

        # Check user info
        user_data = response.data["user"]
        assert user_data["id"] == str(target_user.id)
        assert user_data["username"] == target_user.username

        # Check participation metrics
        participation = response.data["participation"]
        assert participation["discussions_joined"] >= 1
        assert participation["responses_posted"] >= 2

    def test_get_user_analytics_nonexistent_user(self, admin_client):
        """Test getting analytics for non-existent user."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = admin_client.get(f"/api/admin/users/{fake_id}/analytics/")

        assert response.status_code == 404

    def test_get_user_analytics_requires_admin(
        self, authenticated_client, user_factory
    ):
        """Test that user analytics require admin permission."""
        target_user = user_factory()

        response = authenticated_client.get(
            f"/api/admin/users/{target_user.id}/analytics/"
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestFlagUser:
    """Test user flagging endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_flag_user(self, mock_notify, admin_client, user_factory):
        """Test flagging a user for review."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/flag/",
            {"reason": "Suspicious activity", "notes": "Multiple spam posts"},
        )

        assert response.status_code == 200
        assert "flag_id" in response.data
        assert response.data["flagged"] is True

        # Check flag was created
        flag = AdminFlag.objects.get(id=response.data["flag_id"])
        assert flag.user == target_user
        assert flag.flagged_by == admin_client.user
        assert "Suspicious activity" in flag.reason

    def test_flag_user_missing_reason(self, admin_client, user_factory):
        """Test flagging user without reason."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/flag/", {}
        )

        assert response.status_code == 400
        assert "Reason is required" in response.data["error"]

    def test_flag_user_nonexistent_user(self, admin_client):
        """Test flagging non-existent user."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = admin_client.post(
            f"/api/admin/users/{fake_id}/flag/", {"reason": "Test"}
        )

        assert response.status_code == 404

    def test_flag_user_requires_admin(self, authenticated_client, user_factory):
        """Test that flagging requires admin permission."""
        target_user = user_factory()

        response = authenticated_client.post(
            f"/api/admin/users/{target_user.id}/flag/", {"reason": "Test"}
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestBanUser:
    """Test user banning endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_ban_user_permanent(self, mock_notify, admin_client, user_factory):
        """Test permanently banning a user."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/",
            {"reason": "Repeated ToS violations"},
        )

        assert response.status_code == 200
        assert response.data["banned"] is True
        assert response.data["permanent"] is True

        # Check user is banned
        target_user.refresh_from_db()
        assert target_user.is_active is False
        assert target_user.is_banned() is True

        # Check ban record
        ban = UserBan.objects.get(user=target_user)
        assert ban.is_permanent is True
        assert ban.banned_by == admin_client.user

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_ban_user_temporary(self, mock_notify, admin_client, user_factory):
        """Test temporarily banning a user."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/",
            {"reason": "Minor violation", "duration_days": 7},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["banned"] is True
        assert response.data["permanent"] is False

        # Check ban record
        ban = UserBan.objects.get(user=target_user)
        assert ban.is_permanent is False
        assert ban.duration_days == 7
        assert ban.expires_at is not None

    def test_ban_user_missing_reason(self, admin_client, user_factory):
        """Test banning user without reason."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/", {}
        )

        assert response.status_code == 400
        assert "Reason is required" in response.data["error"]

    def test_ban_user_already_banned(self, admin_client, user_factory):
        """Test banning an already-banned user."""
        target_user = user_factory()

        # Ban the user first
        UserBan.objects.create(
            user=target_user,
            banned_by=admin_client.user,
            reason="First ban",
            is_permanent=True,
        )
        target_user.is_active = False
        target_user.save()

        # Try to ban again
        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/", {"reason": "Second ban"}
        )

        assert response.status_code == 400
        assert "already banned" in response.data["error"]

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_ban_user_removes_from_discussions(
        self, mock_notify, admin_client, user_factory, discussion_factory
    ):
        """Test that banning removes user from active discussions."""
        target_user = user_factory()
        discussion = discussion_factory()

        # Make user an active participant
        participant = DiscussionParticipant.objects.create(
            discussion=discussion, user=target_user, role="active"
        )

        # Ban the user
        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/",
            {"reason": "Test ban"},
        )

        assert response.status_code == 200

        # Check participant is now permanent observer
        participant.refresh_from_db()
        assert participant.role == "permanent_observer"

    def test_ban_user_requires_admin(self, authenticated_client, user_factory):
        """Test that banning requires admin permission."""
        target_user = user_factory()

        response = authenticated_client.post(
            f"/api/admin/users/{target_user.id}/ban/", {"reason": "Test"}
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestUnbanUser:
    """Test user unbanning endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_unban_user(self, mock_notify, admin_client, user_factory):
        """Test unbanning a banned user."""
        target_user = user_factory()

        # Ban the user first
        UserBan.objects.create(
            user=target_user,
            banned_by=admin_client.user,
            reason="Initial ban",
            is_permanent=True,
        )
        target_user.is_active = False
        target_user.save()

        # Unban the user
        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/unban/",
            {"reason": "Ban lifted after appeal"},
        )

        assert response.status_code == 200
        assert response.data["unbanned"] is True

        # Check user is unbanned
        target_user.refresh_from_db()
        assert target_user.is_active is True
        assert target_user.is_banned() is False

        # Check ban record is updated
        ban = UserBan.objects.get(user=target_user)
        assert ban.is_active is False
        assert ban.lifted_by == admin_client.user
        assert ban.lift_reason == "Ban lifted after appeal"

    def test_unban_user_not_banned(self, admin_client, user_factory):
        """Test unbanning a user who is not banned."""
        target_user = user_factory()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/unban/",
            {"reason": "Test"},
        )

        assert response.status_code == 400
        assert "not banned" in response.data["error"]

    def test_unban_user_missing_reason(self, admin_client, user_factory):
        """Test unbanning without reason."""
        target_user = user_factory()

        # Ban the user first
        UserBan.objects.create(
            user=target_user,
            banned_by=admin_client.user,
            reason="Initial ban",
            is_permanent=True,
        )
        target_user.is_active = False
        target_user.save()

        # Try to unban without reason
        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/unban/", {}
        )

        assert response.status_code == 400
        assert "Reason is required" in response.data["error"]

    def test_unban_user_requires_admin(self, authenticated_client, user_factory):
        """Test that unbanning requires admin permission."""
        target_user = user_factory()

        response = authenticated_client.post(
            f"/api/admin/users/{target_user.id}/unban/", {"reason": "Test"}
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestVerifyUserPhone:
    """Test manual phone verification endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_verify_user_phone(self, mock_notify, admin_client, user_factory):
        """Test manually verifying a user's phone."""
        target_user = user_factory()
        target_user.phone_verified = False
        target_user.save()

        response = admin_client.post(
            f"/api/admin/users/{target_user.id}/verify-phone/"
        )

        assert response.status_code == 200
        assert response.data["verified"] is True

        # Check user phone is verified
        target_user.refresh_from_db()
        assert target_user.phone_verified is True

    def test_verify_user_phone_nonexistent_user(self, admin_client):
        """Test verifying phone for non-existent user."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = admin_client.post(f"/api/admin/users/{fake_id}/verify-phone/")

        assert response.status_code == 404

    def test_verify_user_phone_requires_admin(
        self, authenticated_client, user_factory
    ):
        """Test that phone verification requires admin permission."""
        target_user = user_factory()

        response = authenticated_client.post(
            f"/api/admin/users/{target_user.id}/verify-phone/"
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestModerationQueue:
    """Test moderation queue endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_moderation_queue_empty(self, admin_client):
        """Test getting empty moderation queue."""
        response = admin_client.get("/api/admin/moderation-queue/")

        assert response.status_code == 200
        assert "flagged_users" in response.data
        assert "suspicious_activity" in response.data
        assert "pending_count" in response.data
        assert response.data["pending_count"] == 0

    def test_get_moderation_queue_with_flags(
        self, admin_client, user_factory
    ):
        """Test getting moderation queue with flagged users."""
        target_user1 = user_factory()
        target_user2 = user_factory()

        # Create flags
        AdminFlag.objects.create(
            user=target_user1,
            flagged_by=admin_client.user,
            reason="Spam detected",
            detection_type="spam",
            confidence=0.85,
            status="pending",
        )
        AdminFlag.objects.create(
            user=target_user2,
            flagged_by=None,  # System flag
            reason="Multiple accounts",
            detection_type="multi_account",
            confidence=0.92,
            status="pending",
        )

        # Create resolved flag (should not appear)
        AdminFlag.objects.create(
            user=user_factory(),
            flagged_by=admin_client.user,
            reason="False positive",
            status="resolved",
        )

        response = admin_client.get("/api/admin/moderation-queue/")

        assert response.status_code == 200
        assert len(response.data["flagged_users"]) == 2
        assert response.data["pending_count"] == 2

        # Check flag data structure
        flag = response.data["flagged_users"][0]
        assert "flag_id" in flag
        assert "user_id" in flag
        assert "username" in flag
        assert "reason" in flag
        assert "flagged_by" in flag
        assert "flagged_at" in flag
        assert "abuse_scores" in flag

    def test_get_moderation_queue_requires_admin(self, authenticated_client):
        """Test that moderation queue requires admin permission."""
        response = authenticated_client.get("/api/admin/moderation-queue/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestResolveFlag:
    """Test flag resolution endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_resolve_flag(self, mock_notify, admin_client, user_factory):
        """Test resolving a flag."""
        target_user = user_factory()

        flag = AdminFlag.objects.create(
            user=target_user,
            flagged_by=user_factory(is_staff=True),
            reason="Test flag",
            status="pending",
        )

        response = admin_client.post(
            f"/api/admin/moderation-queue/{flag.id}/resolve/",
            {"resolution": "no_action", "notes": "False positive"},
        )

        assert response.status_code == 200
        assert response.data["resolved"] is True

        # Check flag is resolved
        flag.refresh_from_db()
        assert flag.status == "resolved"
        assert flag.resolution == "no_action"
        assert flag.resolution_notes == "False positive"
        assert flag.resolved_by == admin_client.user

    def test_resolve_flag_missing_resolution(self, admin_client, user_factory):
        """Test resolving flag without resolution."""
        flag = AdminFlag.objects.create(
            user=user_factory(),
            flagged_by=admin_client.user,
            reason="Test",
            status="pending",
        )

        response = admin_client.post(
            f"/api/admin/moderation-queue/{flag.id}/resolve/", {}
        )

        assert response.status_code == 400
        assert "Resolution is required" in response.data["error"]

    def test_resolve_flag_already_resolved(self, admin_client, user_factory):
        """Test resolving an already-resolved flag."""
        flag = AdminFlag.objects.create(
            user=user_factory(),
            flagged_by=admin_client.user,
            reason="Test",
            status="resolved",
            resolution="no_action",
        )

        response = admin_client.post(
            f"/api/admin/moderation-queue/{flag.id}/resolve/",
            {"resolution": "warned", "notes": "Test"},
        )

        assert response.status_code == 400
        assert "already resolved" in response.data["error"]

    def test_resolve_flag_nonexistent(self, admin_client):
        """Test resolving non-existent flag."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = admin_client.post(
            f"/api/admin/moderation-queue/{fake_id}/resolve/",
            {"resolution": "no_action", "notes": "Test"},
        )

        assert response.status_code == 404

    def test_resolve_flag_requires_admin(
        self, authenticated_client, user_factory
    ):
        """Test that resolving flags requires admin permission."""
        flag = AdminFlag.objects.create(
            user=user_factory(),
            flagged_by=user_factory(is_staff=True),
            reason="Test",
            status="pending",
        )

        response = authenticated_client.post(
            f"/api/admin/moderation-queue/{flag.id}/resolve/",
            {"resolution": "no_action", "notes": "Test"},
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestAdminWorkflows:
    """Test complete admin workflows."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.notification_service.NotificationService.send_notification")
    def test_complete_flag_to_ban_workflow(
        self, mock_notify, admin_client, user_factory
    ):
        """Test complete workflow from flagging to banning a user."""
        target_user = user_factory()

        # Step 1: Flag the user
        flag_response = admin_client.post(
            f"/api/admin/users/{target_user.id}/flag/",
            {"reason": "Repeated spam", "notes": "Multiple reports"},
        )
        assert flag_response.status_code == 200
        flag_id = flag_response.data["flag_id"]

        # Step 2: Check moderation queue
        queue_response = admin_client.get("/api/admin/moderation-queue/")
        assert queue_response.status_code == 200
        assert len(queue_response.data["flagged_users"]) >= 1

        # Step 3: Get user analytics
        analytics_response = admin_client.get(
            f"/api/admin/users/{target_user.id}/analytics/"
        )
        assert analytics_response.status_code == 200

        # Step 4: Ban the user
        ban_response = admin_client.post(
            f"/api/admin/users/{target_user.id}/ban/",
            {"reason": "Confirmed spam activity", "duration_days": 30},
            format="json",
        )
        assert ban_response.status_code == 200

        # Step 5: Resolve the flag
        resolve_response = admin_client.post(
            f"/api/admin/moderation-queue/{flag_id}/resolve/",
            {"resolution": "banned", "notes": "User banned for 30 days"},
        )
        assert resolve_response.status_code == 200

        # Verify final state
        target_user.refresh_from_db()
        assert target_user.is_banned() is True

        flag = AdminFlag.objects.get(id=flag_id)
        assert flag.status == "resolved"
