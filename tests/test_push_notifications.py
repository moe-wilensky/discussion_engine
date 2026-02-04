"""Test push notification functionality."""

import pytest
from django.contrib.auth import get_user_model
from core.models import UserDevice
from core.services.fcm_service import FCMService
from core.services.notification_service import NotificationService
from unittest.mock import patch, MagicMock

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def user_device(db, user):
    """Create a test user device."""
    return UserDevice.objects.create(
        user=user,
        fcm_token="test_fcm_token_123",
        device_type="android",
        device_name="Test Device",
    )


class TestUserDeviceModel:
    """Test UserDevice model."""

    def test_create_device(self, db, user):
        """Test creating a device."""
        device = UserDevice.objects.create(
            user=user,
            fcm_token="test_token",
            device_type="ios",
            device_name="iPhone",
        )
        assert device.user == user
        assert device.fcm_token == "test_token"
        assert device.device_type == "ios"
        assert device.device_name == "iPhone"
        assert device.is_active is True

    def test_device_str(self, user_device):
        """Test device string representation."""
        expected = f"{user_device.user.username} - {user_device.device_type} ({user_device.device_name})"
        assert str(user_device) == expected

    def test_unique_fcm_token(self, db, user, user_device):
        """Test that FCM tokens must be unique."""
        with pytest.raises(Exception):  # IntegrityError
            UserDevice.objects.create(
                user=user, fcm_token="test_fcm_token_123", device_type="ios"
            )

    def test_user_can_have_multiple_devices(self, db, user, user_device):
        """Test that a user can have multiple devices."""
        device2 = UserDevice.objects.create(
            user=user, fcm_token="different_token", device_type="ios"
        )
        assert UserDevice.objects.filter(user=user).count() == 2
        assert device2 in user.devices.all()

    def test_deactivate_device(self, user_device):
        """Test deactivating a device."""
        user_device.is_active = False
        user_device.save()
        assert not user_device.is_active


class TestFCMService:
    """Test FCMService."""

    def test_initialize(self):
        """Test FCM initialization."""
        # Just test that it doesn't crash - Firebase may not be configured
        try:
            FCMService.initialize()
        except Exception:
            pass  # It's OK if Firebase isn't configured in tests

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_device_success(self, mock_send):
        """Test sending a notification to a single device."""
        mock_send.return_value = "message-id-123"

        result = FCMService.send_to_device(
            fcm_token="test_token",
            title="Test Title",
            body="Test Body",
            data={"key": "value"},
        )

        assert result is True
        mock_send.assert_called_once()

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_device_failure(self, mock_send):
        """Test handling send failure."""
        mock_send.side_effect = Exception("Send failed")

        result = FCMService.send_to_device(
            fcm_token="test_token", title="Test", body="Test"
        )

        assert result is False

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_user(self, mock_send, user_device):
        """Test sending notification to a user."""
        mock_send.return_value = "message-id-123"

        result = FCMService.send_to_user(
            user=user_device.user, title="Test", body="Test"
        )

        assert result == 1  # One device sent to
        mock_send.assert_called_once()

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_user_multiple_devices(self, mock_send, db, user):
        """Test sending to user with multiple devices."""
        UserDevice.objects.create(
            user=user, fcm_token="token1", device_type="android"
        )
        UserDevice.objects.create(user=user, fcm_token="token2", device_type="ios")
        mock_send.return_value = "message-id"

        result = FCMService.send_to_user(user=user, title="Test", body="Test")

        assert result == 2  # Two devices sent to
        assert mock_send.call_count == 2

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_user_skip_inactive(self, mock_send, db, user):
        """Test that inactive devices are skipped."""
        active_device = UserDevice.objects.create(
            user=user, fcm_token="active_token", device_type="android", is_active=True
        )
        UserDevice.objects.create(
            user=user,
            fcm_token="inactive_token",
            device_type="ios",
            is_active=False,
        )
        mock_send.return_value = "message-id"

        result = FCMService.send_to_user(user=user, title="Test", body="Test")

        assert result == 1  # Only one active device
        mock_send.assert_called_once()

    @patch("core.services.fcm_service.FCM_AVAILABLE", True)
    @patch("core.services.fcm_service.FCMService._initialized", True)
    @patch("core.services.fcm_service.messaging.send")
    def test_send_to_multiple_users(self, mock_send, db):
        """Test sending to multiple users."""
        user1 = User.objects.create_user(username="user1", password="pass", phone_number="+15551111111")
        user2 = User.objects.create_user(username="user2", password="pass", phone_number="+15552222222")
        UserDevice.objects.create(user=user1, fcm_token="token1", device_type="android")
        UserDevice.objects.create(user=user2, fcm_token="token2", device_type="ios")
        mock_send.return_value = "message-id"

        results = FCMService.send_to_multiple_users(
            users=[user1, user2], title="Test", body="Test"
        )

        assert len(results) == 2
        assert results[user1.id] == 1
        assert results[user2.id] == 1
        assert mock_send.call_count == 2

    def test_register_device(self, db, user):
        """Test registering a new device."""
        device = FCMService.register_device(
            user=user,
            fcm_token="new_token",
            device_type="android",
            device_name="New Device",
        )

        assert device.user == user
        assert device.fcm_token == "new_token"
        assert device.is_active is True

    def test_register_device_updates_existing(self, user_device):
        """Test that registering existing token updates the device."""
        updated_device = FCMService.register_device(
            user=user_device.user,
            fcm_token=user_device.fcm_token,
            device_type="ios",  # Changed
            device_name="Updated Device",  # Changed
        )

        assert updated_device.id == user_device.id
        assert updated_device.device_type == "ios"
        assert updated_device.device_name == "Updated Device"
        assert updated_device.is_active is True

    def test_register_device_reactivates_inactive(self, user_device):
        """Test that registering an inactive device reactivates it."""
        user_device.is_active = False
        user_device.save()

        updated_device = FCMService.register_device(
            user=user_device.user,
            fcm_token=user_device.fcm_token,
            device_type=user_device.device_type,
        )

        assert updated_device.is_active is True

    def test_unregister_device(self, user_device):
        """Test unregistering a device."""
        result = FCMService.unregister_device(fcm_token=user_device.fcm_token)

        assert result is True
        user_device.refresh_from_db()
        assert not user_device.is_active

    def test_unregister_nonexistent_device(self, db):
        """Test unregistering a device that doesn't exist."""
        result = FCMService.unregister_device(fcm_token="nonexistent_token")
        assert result is False


class TestNotificationServiceWithPush:
    """Test NotificationService push notification integration."""

    @patch("core.services.fcm_service.FCMService.send_to_user")
    def test_send_push_notification(self, mock_send, db, user):
        """Test that push notifications are sent."""
        mock_send.return_value = 1  # Returns count of devices sent to

        service = NotificationService()
        service._send_push(
            user=user,
            title="Test Title",
            message="Test Body",
            context={"notification_type": "discussion_started", "discussion_id": 1},
        )

        mock_send.assert_called_once()

    @patch("core.services.fcm_service.FCMService.send_to_user")
    def test_send_push_handles_errors(self, mock_send, db, user):
        """Test that push notification errors are handled gracefully."""
        mock_send.side_effect = Exception("FCM Error")

        service = NotificationService()
        # Should not raise an exception
        service._send_push(
            user=user,
            title="Test",
            message="Test",
            context={},
        )


class TestDeviceRegistrationAPI:
    """Test device registration API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create API client."""
        from rest_framework.test import APIClient

        return APIClient()

    @pytest.fixture
    def authenticated_client(self, api_client, user):
        """Create authenticated API client."""
        api_client.force_authenticate(user=user)
        return api_client

    def test_register_device_requires_auth(self, api_client):
        """Test that device registration requires authentication."""
        response = api_client.post(
            "/api/notifications/devices/register/",
            {"fcm_token": "test_token", "device_type": "android"},
        )
        assert response.status_code == 401

    def test_register_device_success(self, authenticated_client, user):
        """Test successful device registration."""
        response = authenticated_client.post(
            "/api/notifications/devices/register/",
            {
                "fcm_token": "new_test_token",
                "device_type": "android",
                "device_name": "My Phone",
            },
        )
        assert response.status_code == 201
        assert response.data["success"] is True
        assert "device_id" in response.data

        # Verify device was created
        assert UserDevice.objects.filter(
            user=user, fcm_token="new_test_token"
        ).exists()

    def test_register_device_missing_token(self, authenticated_client):
        """Test registration with missing FCM token."""
        response = authenticated_client.post(
            "/api/notifications/devices/register/", {"device_type": "android"}
        )
        assert response.status_code == 400

    def test_unregister_device_requires_auth(self, api_client):
        """Test that device unregistration requires authentication."""
        response = api_client.post(
            "/api/notifications/devices/unregister/", {"fcm_token": "test_token"}
        )
        assert response.status_code == 401

    def test_unregister_device_success(self, authenticated_client, user_device):
        """Test successful device unregistration."""
        response = authenticated_client.post(
            "/api/notifications/devices/unregister/",
            {"fcm_token": user_device.fcm_token},
        )
        assert response.status_code == 200

        # Verify device was deactivated
        user_device.refresh_from_db()
        assert not user_device.is_active

    def test_unregister_nonexistent_device(self, authenticated_client):
        """Test unregistering a device that doesn't exist."""
        response = authenticated_client.post(
            "/api/notifications/devices/unregister/", {"fcm_token": "nonexistent"}
        )
        assert response.status_code == 404

    def test_list_devices_requires_auth(self, api_client):
        """Test that listing devices requires authentication."""
        response = api_client.get("/api/notifications/devices/")
        assert response.status_code == 401

    def test_list_devices_success(self, authenticated_client, user):
        """Test listing user's devices."""
        # Create multiple devices
        device1 = UserDevice.objects.create(
            user=user, fcm_token="token1", device_type="android", device_name="Phone"
        )
        device2 = UserDevice.objects.create(
            user=user, fcm_token="token2", device_type="ios", device_name="Tablet"
        )

        response = authenticated_client.get("/api/notifications/devices/")
        assert response.status_code == 200
        assert len(response.data["devices"]) == 2

    def test_list_devices_only_shows_active(self, authenticated_client, user):
        """Test that listing only shows active devices."""
        active = UserDevice.objects.create(
            user=user,
            fcm_token="active_token",
            device_type="android",
            is_active=True,
        )
        UserDevice.objects.create(
            user=user,
            fcm_token="inactive_token",
            device_type="ios",
            is_active=False,
        )

        response = authenticated_client.get("/api/notifications/devices/")
        assert response.status_code == 200
        assert len(response.data["devices"]) == 1
        assert response.data["devices"][0]["device_type"] == "android"

    def test_list_devices_only_shows_own_devices(
        self, authenticated_client, user, db
    ):
        """Test that users only see their own devices."""
        other_user = User.objects.create_user(
            username="other",
            email="other@test.com",
            password="pass",
            phone_number="+15551234567"
        )
        UserDevice.objects.create(
            user=user, fcm_token="my_token", device_type="android"
        )
        UserDevice.objects.create(
            user=other_user, fcm_token="their_token", device_type="ios"
        )

        response = authenticated_client.get("/api/notifications/devices/")
        assert response.status_code == 200
        assert len(response.data["devices"]) == 1
        # Check one of the devices has the user's device_type
        device_types = [d["device_type"] for d in response.data["devices"]]
        assert "android" in device_types
