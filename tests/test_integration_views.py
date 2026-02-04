"""
Integration Tests for Views - Real Database Testing

These tests verify the complete integration of Views, Models, and Templates
without mocking. They catch FieldErrors and TemplateDoesNotExist errors that
unit tests miss.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import (
    Discussion,
    DiscussionParticipant,
    Invite,
    PlatformConfig,
    Round,
    Response,
    NotificationLog,
    JoinRequest,
)

User = get_user_model()


class ViewIntegrationTestCase(TestCase):
    """Base class for view integration tests with common setup."""

    def setUp(self):
        """Set up test data that hits the real database."""
        # Create platform config
        self.config = PlatformConfig.load()

        # Create test users
        self.user1 = User.objects.create_user(
            username="testuser1",
            email="test1@example.com",
            password="testpass123",
            phone_number="+1234567890",
            phone_verified=True,
            platform_invites_banked=5,
            discussion_invites_banked=10,
        )

        self.user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123",
            phone_number="+1234567891",
            phone_verified=True,
        )

        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
            phone_number="+1234567892",
            is_staff=True,
            is_platform_admin=True,
        )

        # Create a discussion
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="This is a test discussion for integration testing",
            max_response_length_chars=1000,
            response_time_multiplier=1.5,
            min_response_time_minutes=30,
            initiator=self.user1,
        )

        # Add participant
        self.participant = DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user1, role="initiator"
        )

        # Create a round
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, final_mrp_minutes=60.0
        )

        # Create client
        self.client = Client()


class AuthenticationViewTests(ViewIntegrationTestCase):
    """Test authentication views for field/template errors."""

    def test_login_view_loads(self):
        """Test login page loads successfully."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth/login.html")
        self.assertContains(response, "username")

    def test_register_view_loads(self):
        """Test registration page loads successfully."""
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth/register.html")

    def test_verify_phone_view_loads(self):
        """Test phone verification page loads successfully."""
        response = self.client.get(reverse("verify-phone"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth/verify_phone.html")

    def test_password_reset_view_loads(self):
        """Test password reset page loads successfully."""
        response = self.client.get(reverse("password-reset"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth/password_reset.html")

    def test_login_with_valid_credentials(self):
        """Test login with valid credentials."""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser1", "password": "testpass123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["user"].is_authenticated)

    def test_logout_view(self):
        """Test logout functionality."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("logout"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class DashboardViewTests(ViewIntegrationTestCase):
    """Test dashboard views for field/template errors."""

    def test_dashboard_view_requires_login(self):
        """Test dashboard redirects unauthenticated users."""
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_view_loads_for_authenticated_user(self):
        """Test dashboard loads for authenticated user with real data."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/home.html")

        # Verify context data is present
        self.assertIn("stats", response.context)
        self.assertIn("active_discussions", response.context)
        self.assertIn("pending_invites", response.context)
        self.assertIn("recent_notifications", response.context)

        # Verify stats dictionary has expected keys
        stats = response.context["stats"]
        self.assertIn("active_discussions", stats)
        self.assertIn("responses_posted", stats)
        self.assertIn("pending_invites", stats)
        self.assertIn("unread_notifications", stats)

    def test_invites_view_loads_with_sent_at_field(self):
        """
        CRITICAL TEST: Verify invites view uses correct field name 'sent_at'.
        This test catches the FieldError: created_at does not exist on Invite model.
        """
        # Create test invites
        invite1 = Invite.objects.create(
            inviter=self.user1,
            invitee=self.user2,
            invite_type="platform",
            status="sent",
        )

        invite2 = Invite.objects.create(
            inviter=self.user2,
            invitee=self.user1,
            invite_type="discussion",
            discussion=self.discussion,
            status="sent",
        )

        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("invites"))

        # This will raise FieldError if view queries wrong field name
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/invites.html")

        # Verify context contains invites
        self.assertIn("received_invites", response.context)
        self.assertIn("sent_invites", response.context)

        # Verify invites are actually in the context
        received = response.context["received_invites"]
        sent = response.context["sent_invites"]

        # User1 should have 1 received and 1 sent
        self.assertEqual(received.count(), 1)
        self.assertEqual(sent.count(), 1)

        # Verify the template renders with sent_at field
        self.assertContains(response, "Sent")

    def test_notifications_view_loads(self):
        """Test notifications page loads with real data."""
        # Create test notification
        NotificationLog.objects.create(
            user=self.user1,
            notification_type="new_response",
            title="Test Notification",
            message="This is a test notification",
        )

        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/notifications.html")

        # Verify context
        self.assertIn("notifications", response.context)
        self.assertIn("unread_count", response.context)

    def test_user_settings_view_loads(self):
        """
        CRITICAL TEST: Verify settings template exists.
        This test catches TemplateDoesNotExist: dashboard/settings.html.
        """
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("user-settings"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/settings.html")

        # Verify user context is available
        self.assertEqual(response.context["user"], self.user1)

        # Verify template renders user data
        self.assertContains(response, self.user1.username)
        self.assertContains(response, self.user1.phone_number)


class DiscussionViewTests(ViewIntegrationTestCase):
    """Test discussion views for field/template errors."""

    def test_discussion_create_view_loads(self):
        """Test discussion creation form loads."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("discussion-create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "discussions/create.html")

    def test_discussion_list_view_loads(self):
        """Test discussion list loads with real data."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("discussion-list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "discussions/list.html")

        # Verify context
        self.assertIn("discussions", response.context)
        self.assertTrue(response.context["discussions"].count() > 0)

    def test_discussion_detail_view_loads(self):
        """Test discussion detail loads with real data."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("discussion-detail", kwargs={"discussion_id": self.discussion.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "discussions/detail.html")

        # Verify context
        self.assertIn("discussion", response.context)
        self.assertIn("participant", response.context)
        self.assertIn("responses", response.context)
        self.assertIn("participants", response.context)

        self.assertEqual(response.context["discussion"], self.discussion)

    def test_discussion_participate_view_loads(self):
        """Test participate form loads for eligible users."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("discussion-participate", kwargs={"discussion_id": self.discussion.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "discussions/participate.html")

        # Verify context
        self.assertIn("discussion", response.context)
        self.assertIn("participant", response.context)
        self.assertIn("max_chars", response.context)

    def test_discussion_voting_view_requires_voting_phase(self):
        """Test voting view checks discussion status."""
        self.client.login(username="testuser1", password="testpass123")

        # Discussion is not in voting phase
        response = self.client.get(
            reverse("discussion-voting", kwargs={"discussion_id": self.discussion.id}),
            follow=True,
        )

        # Should redirect with error message
        self.assertContains(response, "not in voting phase")

    def test_discussion_voting_view_loads_in_voting_phase(self):
        """Test voting view loads when discussion is in voting phase."""
        # Set discussion to voting status
        self.discussion.status = "voting"
        self.discussion.save()

        self.round.status = "voting"
        self.round.save()

        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("discussion-voting", kwargs={"discussion_id": self.discussion.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "discussions/voting.html")


class ModerationViewTests(ViewIntegrationTestCase):
    """Test moderation views for field/template errors."""

    def test_moderation_history_view_loads(self):
        """Test moderation history page loads."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("moderation-history", kwargs={"discussion_id": self.discussion.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "moderation/history.html")

        # Verify context
        self.assertIn("discussion", response.context)


class AdminViewTests(ViewIntegrationTestCase):
    """Test admin views for field/template errors."""

    def test_admin_dashboard_requires_staff(self):
        """Test admin dashboard requires staff permission."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("admin-dashboard"))

        # Should redirect to login or show forbidden
        self.assertIn(response.status_code, [302, 403])

    def test_admin_dashboard_loads_for_staff(self):
        """Test admin dashboard loads for staff users."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(reverse("admin-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/dashboard.html")

        # Verify context
        self.assertIn("stats", response.context)

    def test_admin_config_view_loads(self):
        """Test platform config editor loads."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(reverse("admin-config"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/config.html")

        # Verify config is in context
        self.assertIn("config", response.context)
        self.assertEqual(response.context["config"], self.config)

    def test_admin_analytics_view_loads(self):
        """Test analytics dashboard loads."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(reverse("admin-analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/analytics.html")

        # Verify analytics context
        self.assertIn("analytics", response.context)

    def test_admin_moderation_queue_view_loads(self):
        """Test moderation queue loads."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(reverse("admin-moderation-queue"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/moderation_queue.html")

        # Verify flagged users context
        self.assertIn("flagged_users", response.context)


class HTMXEndpointTests(ViewIntegrationTestCase):
    """Test HTMX/AJAX endpoints for field/template errors."""

    def test_user_search_endpoint(self):
        """Test user search HTMX endpoint."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("user-search"), {"q": "test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Verify JSON structure
        data = response.json()
        self.assertIn("users", data)

    def test_mark_notification_read_endpoint(self):
        """Test mark notification as read endpoint."""
        notification = NotificationLog.objects.create(
            user=self.user1,
            notification_type="test",
            title="Test",
            message="Test notification",
        )

        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("mark-notification-read", kwargs={"notification_id": notification.id})
        )

        self.assertEqual(response.status_code, 200)

        # Verify notification was marked as read
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)


class FieldNameConsistencyTests(ViewIntegrationTestCase):
    """Tests specifically for field name consistency across models and views."""

    def test_invite_model_uses_sent_at_not_created_at(self):
        """Verify Invite model has sent_at field, not created_at."""
        invite = Invite.objects.create(
            inviter=self.user1, invitee=self.user2, invite_type="platform"
        )

        # This should work
        self.assertIsNotNone(invite.sent_at)

        # This should fail if created_at doesn't exist
        with self.assertRaises(AttributeError):
            _ = invite.created_at

    def test_notification_model_uses_created_at(self):
        """Verify NotificationLog model has created_at field."""
        notif = NotificationLog.objects.create(
            user=self.user1, notification_type="test", title="Test", message="Test"
        )

        # This should work
        self.assertIsNotNone(notif.created_at)
        self.assertIsNotNone(notif.read_at is not None or notif.read_at is None)

    def test_response_model_uses_created_at(self):
        """Verify Response model has created_at field."""
        response = Response.objects.create(
            round=self.round,
            user=self.user1,
            content="Test response content for field testing",
        )

        # This should work
        self.assertIsNotNone(response.created_at)

    def test_discussion_model_uses_created_at(self):
        """Verify Discussion model has created_at field."""
        # This should work
        self.assertIsNotNone(self.discussion.created_at)


class TemplateContextTests(ViewIntegrationTestCase):
    """Tests to verify template context variables match what views pass."""

    def test_dashboard_context_variables(self):
        """Verify dashboard passes all required context variables."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("dashboard"))

        required_vars = [
            "stats",
            "active_discussions",
            "pending_invites",
            "recent_notifications",
        ]

        for var in required_vars:
            self.assertIn(
                var, response.context, f"Missing required context variable: {var}"
            )

    def test_invites_context_variables(self):
        """Verify invites view passes all required context variables."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(reverse("invites"))

        required_vars = [
            "received_invites",
            "sent_invites",
            "platform_invites_banked",
            "discussion_invites_banked",
        ]

        for var in required_vars:
            self.assertIn(
                var, response.context, f"Missing required context variable: {var}"
            )

    def test_discussion_detail_context_variables(self):
        """Verify discussion detail passes all required context variables."""
        self.client.login(username="testuser1", password="testpass123")
        response = self.client.get(
            reverse("discussion-detail", kwargs={"discussion_id": self.discussion.id})
        )

        required_vars = [
            "discussion",
            "participant",
            "responses",
            "participants",
            "can_respond",
            "is_observer",
        ]

        for var in required_vars:
            self.assertIn(
                var, response.context, f"Missing required context variable: {var}"
            )
