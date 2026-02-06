"""
Comprehensive integration tests for notification API endpoints.

Tests all notification-related endpoints including:
- Listing notifications
- Marking notifications as read
- Notification preferences
- Device registration for push notifications
"""

import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta

from core.models import (
    NotificationLog,
    NotificationPreference,
    UserDevice,
    User,
    PlatformConfig,
)
from core.services.notification_service import NotificationService


@pytest.mark.django_db
class TestListNotifications:
    """Test notification listing endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_list_notifications_empty(self, authenticated_client):
        """Test listing notifications when user has none."""
        response = authenticated_client.get("/api/notifications/")

        assert response.status_code == 200
        assert response.data["count"] == 0
        assert response.data["results"]["unread_count"] == 0
        assert len(response.data["results"]["notifications"]) == 0

    def test_list_notifications_with_data(self, authenticated_client):
        """Test listing notifications with data."""
        user = authenticated_client.user

        # Create notifications
        notif1 = NotificationLog.objects.create(
            user=user,
            notification_type="new_response_posted",
            title="New Response",
            message="Someone posted a response",
            context={"discussion_id": "123"},
            read=False,
        )
        notif2 = NotificationLog.objects.create(
            user=user,
            notification_type="mrp_expiring_soon",
            title="Time Running Out",
            message="You have 15 minutes left",
            context={},
            read=True,
            is_critical=True,
        )

        response = authenticated_client.get("/api/notifications/")

        assert response.status_code == 200
        assert response.data["count"] == 2
        assert response.data["results"]["unread_count"] == 1
        assert len(response.data["results"]["notifications"]) == 2

        # Check notification data
        notifications = response.data["results"]["notifications"]
        assert notifications[0]["id"] == str(notif2.id)
        assert notifications[0]["type"] == "mrp_expiring_soon"
        assert notifications[0]["read"] is True
        assert notifications[0]["is_critical"] is True

        assert notifications[1]["id"] == str(notif1.id)
        assert notifications[1]["read"] is False

    def test_list_notifications_unread_only(self, authenticated_client):
        """Test listing only unread notifications."""
        user = authenticated_client.user

        # Create mix of read/unread notifications
        NotificationLog.objects.create(
            user=user,
            notification_type="new_response_posted",
            title="New Response",
            message="Test",
            read=False,
        )
        NotificationLog.objects.create(
            user=user,
            notification_type="round_ended",
            title="Round Ended",
            message="Test",
            read=True,
        )
        NotificationLog.objects.create(
            user=user,
            notification_type="voting_opened",
            title="Voting Open",
            message="Test",
            read=False,
        )

        response = authenticated_client.get("/api/notifications/?unread_only=true")

        assert response.status_code == 200
        assert len(response.data["results"]["notifications"]) == 2
        assert all(n["read"] is False for n in response.data["results"]["notifications"])

    def test_list_notifications_pagination(self, authenticated_client):
        """Test notification pagination."""
        user = authenticated_client.user

        # Create 25 notifications (default page size is 20)
        for i in range(25):
            NotificationLog.objects.create(
                user=user,
                notification_type="new_response_posted",
                title=f"Notification {i}",
                message="Test",
            )

        # Get first page
        response = authenticated_client.get("/api/notifications/?page=1&page_size=10")

        assert response.status_code == 200
        assert len(response.data["results"]["notifications"]) == 10
        assert response.data["count"] == 25
        assert "next" in response.data

        # Get second page
        response = authenticated_client.get("/api/notifications/?page=2&page_size=10")

        assert response.status_code == 200
        assert len(response.data["results"]["notifications"]) == 10

    def test_list_notifications_requires_auth(self, api_client):
        """Test that listing notifications requires authentication."""
        response = api_client.get("/api/notifications/")

        assert response.status_code in [401, 403]

    def test_list_notifications_user_isolation(
        self, authenticated_client, user_factory
    ):
        """Test that users can only see their own notifications."""
        user1 = authenticated_client.user
        user2 = user_factory()

        # Create notifications for both users
        NotificationLog.objects.create(
            user=user1,
            notification_type="new_response_posted",
            title="User 1 Notification",
            message="Test",
        )
        NotificationLog.objects.create(
            user=user2,
            notification_type="new_response_posted",
            title="User 2 Notification",
            message="Test",
        )

        response = authenticated_client.get("/api/notifications/")

        assert response.status_code == 200
        assert len(response.data["results"]["notifications"]) == 1
        assert response.data["results"]["notifications"][0]["title"] == "User 1 Notification"


@pytest.mark.django_db
class TestMarkNotificationRead:
    """Test marking notifications as read."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_mark_notification_read(self, authenticated_client):
        """Test marking a notification as read."""
        user = authenticated_client.user

        notification = NotificationLog.objects.create(
            user=user,
            notification_type="new_response_posted",
            title="Test",
            message="Test",
            read=False,
        )

        response = authenticated_client.post(
            f"/api/notifications/{notification.id}/mark-read/"
        )

        assert response.status_code == 200
        assert response.data["success"] is True

        # Check notification is marked read
        notification.refresh_from_db()
        assert notification.read is True
        assert notification.read_at is not None

    def test_mark_notification_read_idempotent(self, authenticated_client):
        """Test marking an already-read notification."""
        user = authenticated_client.user

        notification = NotificationLog.objects.create(
            user=user,
            notification_type="new_response_posted",
            title="Test",
            message="Test",
            read=True,
            read_at=timezone.now() - timedelta(hours=1),
        )

        old_read_at = notification.read_at

        response = authenticated_client.post(
            f"/api/notifications/{notification.id}/mark-read/"
        )

        assert response.status_code == 200

        # read_at should not change
        notification.refresh_from_db()
        assert notification.read_at == old_read_at

    def test_mark_notification_read_wrong_user(
        self, authenticated_client, user_factory
    ):
        """Test cannot mark another user's notification as read."""
        other_user = user_factory()

        notification = NotificationLog.objects.create(
            user=other_user,
            notification_type="new_response_posted",
            title="Test",
            message="Test",
            read=False,
        )

        response = authenticated_client.post(
            f"/api/notifications/{notification.id}/mark-read/"
        )

        assert response.status_code == 404

    def test_mark_notification_read_invalid_id(self, authenticated_client):
        """Test marking notification with invalid ID."""
        response = authenticated_client.post(
            "/api/notifications/00000000-0000-0000-0000-000000000000/mark-read/"
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestMarkAllRead:
    """Test marking all notifications as read."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_mark_all_read(self, authenticated_client):
        """Test marking all notifications as read."""
        user = authenticated_client.user

        # Create multiple unread notifications
        for i in range(5):
            NotificationLog.objects.create(
                user=user,
                notification_type="new_response_posted",
                title=f"Test {i}",
                message="Test",
                read=False,
            )

        response = authenticated_client.post("/api/notifications/mark-all-read/")

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["marked_count"] == 5

        # Check all are marked read
        assert NotificationLog.objects.filter(user=user, read=False).count() == 0

    def test_mark_all_read_empty(self, authenticated_client):
        """Test marking all read when there are no unread notifications."""
        response = authenticated_client.post("/api/notifications/mark-all-read/")

        assert response.status_code == 200
        assert response.data["marked_count"] == 0

    def test_mark_all_read_mixed(self, authenticated_client):
        """Test marking all read with mix of read/unread."""
        user = authenticated_client.user

        # Create mix
        for i in range(3):
            NotificationLog.objects.create(
                user=user,
                notification_type="new_response_posted",
                title=f"Unread {i}",
                message="Test",
                read=False,
            )

        for i in range(2):
            NotificationLog.objects.create(
                user=user,
                notification_type="new_response_posted",
                title=f"Read {i}",
                message="Test",
                read=True,
                read_at=timezone.now() - timedelta(hours=1),
            )

        response = authenticated_client.post("/api/notifications/mark-all-read/")

        assert response.status_code == 200
        assert response.data["marked_count"] == 3

    def test_mark_all_read_user_isolation(
        self, authenticated_client, user_factory
    ):
        """Test mark all read only affects current user."""
        user1 = authenticated_client.user
        user2 = user_factory()

        # Create notifications for both users
        NotificationLog.objects.create(
            user=user1,
            notification_type="new_response_posted",
            title="User 1",
            message="Test",
            read=False,
        )
        NotificationLog.objects.create(
            user=user2,
            notification_type="new_response_posted",
            title="User 2",
            message="Test",
            read=False,
        )

        response = authenticated_client.post("/api/notifications/mark-all-read/")

        assert response.status_code == 200
        assert response.data["marked_count"] == 1

        # User 2's notification should still be unread
        assert NotificationLog.objects.filter(user=user2, read=False).count() == 1


@pytest.mark.django_db
class TestDeleteNotification:
    """Test deleting notifications."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_delete_notification(self, authenticated_client):
        """Test deleting a notification."""
        user = authenticated_client.user

        notification = NotificationLog.objects.create(
            user=user,
            notification_type="new_response_posted",
            title="Test",
            message="Test",
        )

        notification_id = notification.id

        response = authenticated_client.delete(f"/api/notifications/{notification_id}/")

        assert response.status_code == 200
        assert response.data["success"] is True

        # Check notification is deleted
        assert not NotificationLog.objects.filter(id=notification_id).exists()

    def test_delete_notification_wrong_user(
        self, authenticated_client, user_factory
    ):
        """Test cannot delete another user's notification."""
        other_user = user_factory()

        notification = NotificationLog.objects.create(
            user=other_user,
            notification_type="new_response_posted",
            title="Test",
            message="Test",
        )

        response = authenticated_client.delete(f"/api/notifications/{notification.id}/")

        assert response.status_code == 404

        # Notification should still exist
        assert NotificationLog.objects.filter(id=notification.id).exists()


@pytest.mark.django_db
class TestNotificationPreferences:
    """Test notification preference endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_notification_preferences(self, authenticated_client):
        """Test getting notification preferences."""
        response = authenticated_client.get("/api/notifications/preferences/")

        assert response.status_code == 200
        assert "preferences" in response.data
        assert len(response.data["preferences"]) > 0

        # Check structure of preferences
        pref = response.data["preferences"][0]
        assert "type" in pref
        assert "enabled" in pref
        assert "is_critical" in pref
        assert "delivery_methods" in pref

    def test_get_notification_preferences_creates_defaults(
        self, authenticated_client
    ):
        """Test that getting preferences creates default preferences."""
        user = authenticated_client.user

        # Should have no preferences initially
        assert NotificationPreference.objects.filter(user=user).count() == 0

        response = authenticated_client.get("/api/notifications/preferences/")

        assert response.status_code == 200

        # Should have created preferences for all notification types
        assert NotificationPreference.objects.filter(user=user).count() > 0

    def test_update_notification_preferences(self, authenticated_client):
        """Test updating notification preferences."""
        user = authenticated_client.user

        # Create initial preference
        NotificationPreference.objects.create(
            user=user,
            notification_type="new_response_posted",
            enabled=True,
            delivery_method={"in_app": True, "email": False, "push": False},
        )

        # Update preference
        response = authenticated_client.patch(
            "/api/notifications/preferences/update/",
            {
                "preferences": [
                    {
                        "type": "new_response_posted",
                        "enabled": False,
                        "delivery_methods": {
                            "in_app": True,
                            "email": True,
                            "push": True,
                        },
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["updated_count"] == 1

        # Check preference was updated
        pref = NotificationPreference.objects.get(
            user=user, notification_type="new_response_posted"
        )
        assert pref.enabled is False
        assert pref.delivery_method["email"] is True
        assert pref.delivery_method["push"] is True

    def test_update_notification_preferences_critical(self, authenticated_client):
        """Test that critical notifications cannot be disabled."""
        user = authenticated_client.user

        # Create critical preference
        NotificationPreference.objects.create(
            user=user,
            notification_type="mrp_expiring_soon",
            enabled=True,
            delivery_method={"in_app": True, "email": False, "push": False},
        )

        # Try to disable it
        response = authenticated_client.patch(
            "/api/notifications/preferences/update/",
            {
                "preferences": [
                    {
                        "type": "mrp_expiring_soon",
                        "enabled": False,
                        "delivery_methods": {"in_app": False, "email": False, "push": False},
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == 200

        # Check preference - enabled should remain True, in_app should remain True
        pref = NotificationPreference.objects.get(
            user=user, notification_type="mrp_expiring_soon"
        )
        # Critical notifications should still have in_app enabled
        assert pref.delivery_method["in_app"] is True

    def test_update_notification_preferences_invalid_format(
        self, authenticated_client
    ):
        """Test updating preferences with invalid format."""
        response = authenticated_client.patch(
            "/api/notifications/preferences/update/",
            {"preferences": "not_a_list"},
            format="json",
        )

        assert response.status_code == 400
        assert "must be a list" in response.data["error"]

    def test_update_notification_preferences_invalid_type(
        self, authenticated_client
    ):
        """Test updating preferences with invalid notification type."""
        response = authenticated_client.patch(
            "/api/notifications/preferences/update/",
            {
                "preferences": [
                    {
                        "type": "invalid_notification_type",
                        "enabled": False,
                    }
                ]
            },
            format="json",
        )

        # Should succeed but skip invalid types
        assert response.status_code == 200
        assert response.data["updated_count"] == 0


@pytest.mark.django_db
class TestDeviceRegistration:
    """Test device registration for push notifications."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    @patch("core.services.fcm_service.FCMService.register_device")
    def test_register_device(self, mock_register, authenticated_client):
        """Test registering a device for push notifications."""
        mock_device = MagicMock()
        mock_device.id = "test-device-id"
        mock_register.return_value = mock_device

        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {
                "fcm_token": "test_fcm_token_123",
                "device_type": "ios",
                "device_name": "Test iPhone",
            },
        )

        assert response.status_code == 201
        assert response.data["success"] is True
        assert "device_id" in response.data
        assert "message" in response.data

        # Check service was called correctly
        mock_register.assert_called_once()
        call_kwargs = mock_register.call_args.kwargs
        assert call_kwargs["user"] == authenticated_client.user
        assert call_kwargs["fcm_token"] == "test_fcm_token_123"
        assert call_kwargs["device_type"] == "ios"
        assert call_kwargs["device_name"] == "Test iPhone"

    def test_register_device_missing_token(self, authenticated_client):
        """Test registering device without FCM token."""
        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {"device_type": "ios"},
        )

        assert response.status_code == 400
        assert "fcm_token" in response.data["error"]

    def test_register_device_missing_type(self, authenticated_client):
        """Test registering device without device type."""
        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {"fcm_token": "test_token"},
        )

        assert response.status_code == 400
        assert "device_type" in response.data["error"]

    def test_register_device_invalid_type(self, authenticated_client):
        """Test registering device with invalid device type."""
        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {"fcm_token": "test_token", "device_type": "invalid"},
        )

        assert response.status_code == 400
        assert "must be ios, android, or web" in response.data["error"]

    @patch("core.services.fcm_service.FCMService.register_device")
    def test_register_device_service_error(self, mock_register, authenticated_client):
        """Test handling service error during device registration."""
        mock_register.side_effect = Exception("Service unavailable")

        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {"fcm_token": "test_token", "device_type": "ios"},
        )

        assert response.status_code == 500
        assert "Failed to register device" in response.data["error"]

    @patch("core.services.fcm_service.FCMService.unregister_device")
    def test_unregister_device(self, mock_unregister, authenticated_client):
        """Test unregistering a device."""
        mock_unregister.return_value = True

        response = authenticated_client.post(
            "/api/notifications/devices/unregister/",
            {"fcm_token": "test_fcm_token_123"},
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert "message" in response.data

        # Check service was called
        mock_unregister.assert_called_once_with("test_fcm_token_123")

    @patch("core.services.fcm_service.FCMService.unregister_device")
    def test_unregister_device_not_found(self, mock_unregister, authenticated_client):
        """Test unregistering a device that doesn't exist."""
        mock_unregister.return_value = False

        response = authenticated_client.post(
            "/api/notifications/devices/unregister/",
            {"fcm_token": "nonexistent_token"},
        )

        assert response.status_code == 404
        assert response.data["success"] is False

    def test_unregister_device_missing_token(self, authenticated_client):
        """Test unregistering device without token."""
        response = authenticated_client.post(
            "/api/notifications/devices/unregister/", {}
        )

        assert response.status_code == 400
        assert "fcm_token is required" in response.data["error"]

    def test_list_devices(self, authenticated_client):
        """Test listing user's registered devices."""
        user = authenticated_client.user

        # Create devices
        UserDevice.objects.create(
            user=user,
            fcm_token="token1",
            device_type="ios",
            device_name="iPhone",
            is_active=True,
        )
        UserDevice.objects.create(
            user=user,
            fcm_token="token2",
            device_type="android",
            device_name="Pixel",
            is_active=True,
        )
        # Create inactive device (should not appear)
        UserDevice.objects.create(
            user=user,
            fcm_token="token3",
            device_type="web",
            device_name="Browser",
            is_active=False,
        )

        response = authenticated_client.get("/api/notifications/devices/")

        assert response.status_code == 200
        assert "devices" in response.data
        assert len(response.data["devices"]) == 2

        # Check device structure
        device = response.data["devices"][0]
        assert "id" in device
        assert "device_type" in device
        assert "device_name" in device
        assert "is_active" in device
        assert "last_used" in device
        assert "created_at" in device

    def test_list_devices_empty(self, authenticated_client):
        """Test listing devices when user has none."""
        response = authenticated_client.get("/api/notifications/devices/")

        assert response.status_code == 200
        assert len(response.data["devices"]) == 0

    def test_list_devices_user_isolation(
        self, authenticated_client, user_factory
    ):
        """Test that users can only see their own devices."""
        user1 = authenticated_client.user
        user2 = user_factory()

        # Create devices for both users
        UserDevice.objects.create(
            user=user1,
            fcm_token="user1_token",
            device_type="ios",
            is_active=True,
        )
        UserDevice.objects.create(
            user=user2,
            fcm_token="user2_token",
            device_type="android",
            is_active=True,
        )

        response = authenticated_client.get("/api/notifications/devices/")

        assert response.status_code == 200
        assert len(response.data["devices"]) == 1
        assert response.data["devices"][0]["device_type"] == "ios"
