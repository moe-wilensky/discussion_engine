"""Tests for template views - auth, dashboard, discussion views, admin, HTMX endpoints."""

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from core.models import (
    User, Discussion, DiscussionParticipant, Round, Response,
    NotificationLog, PlatformConfig, Invite, NotificationPreference,
)


class TestAuthViews(TestCase):
    """Tests for authentication views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )

    def test_register_get(self):
        response = self.client.get(reverse("register"))
        assert response.status_code == 200

    def test_register_post(self):
        response = self.client.post(reverse("register"), {"phone_number": "+15559999999"})
        assert response.status_code == 200
        self.assertTemplateUsed(response, "auth/verify_phone.html")

    def test_register_page_alias(self):
        response = self.client.get(reverse("register-page"))
        assert response.status_code == 200

    def test_verify_phone_get(self):
        response = self.client.get(reverse("verify-phone"))
        assert response.status_code == 200

    def test_verify_phone_post_redirects(self):
        response = self.client.post(reverse("verify-phone"), {})
        assert response.status_code == 302

    def test_resend_verification(self):
        response = self.client.post(reverse("resend-verification"))
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_login_get(self):
        response = self.client.get(reverse("login"))
        assert response.status_code == 200

    def test_login_post_valid_credentials(self):
        response = self.client.post(
            reverse("login"), {"username": "testuser", "password": "testpass123"}
        )
        assert response.status_code == 302
        assert response.url == reverse("dashboard")

    def test_login_post_invalid_credentials(self):
        response = self.client.post(
            reverse("login"), {"username": "testuser", "password": "wrongpass"}
        )
        assert response.status_code == 200  # Re-renders login page

    def test_logout_redirects(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("logout"))
        assert response.status_code == 302

    def test_password_reset(self):
        response = self.client.get(reverse("password-reset"))
        assert response.status_code == 200


class TestDiscussionListView(TestCase):
    """Tests for the discussion list view filters and search."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Some details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_search_filter(self):
        response = self.client.get(reverse("discussion-list"), {"search": "Test"})
        assert response.status_code == 200
        assert self.discussion in response.context["discussions"]

    def test_filter_active(self):
        response = self.client.get(reverse("discussion-list"), {"filter": "active"})
        assert response.status_code == 200

    def test_filter_archived(self):
        response = self.client.get(reverse("discussion-list"), {"filter": "archived"})
        assert response.status_code == 200

    def test_filter_mine(self):
        response = self.client.get(reverse("discussion-list"), {"filter": "mine"})
        assert response.status_code == 200

    def test_htmx_returns_partial(self):
        response = self.client.get(
            reverse("discussion-list"),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


class TestDiscussionActiveView(TestCase):
    """Tests for the active discussion view."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )
        self.client.login(username="testuser", password="testpass123")
        self.url = reverse("discussion-active", kwargs={"discussion_id": self.discussion.id})

    def test_non_participant_redirects_to_observer(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15552222222", password="testpass123"
        )
        self.client.login(username="outsider", password="testpass123")
        response = self.client.get(self.url)
        assert response.status_code == 302
        assert "observer" in response.url

    def test_no_round_redirects_to_dashboard(self):
        self.round.delete()
        response = self.client.get(self.url)
        assert response.status_code == 302

    def test_active_participant_sees_active_view(self):
        response = self.client.get(self.url)
        assert response.status_code == 200
        self.assertTemplateUsed(response, "discussions/active_view.html")
        assert response.context["participant_status"] == "Response pending"

    def test_responded_status_shown(self):
        Response.objects.create(
            round=self.round, user=self.user, content="My response"
        )
        response = self.client.get(self.url)
        assert response.context["participant_status"] == "Responded this round"


class TestDiscussionVotingView(TestCase):
    """Tests for the voting view."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="voting",
            end_time=timezone.now(), final_mrp_minutes=60,
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )
        self.client.login(username="testuser", password="testpass123")
        self.url = reverse("discussion-voting", kwargs={"discussion_id": self.discussion.id})

    def test_non_participant_forbidden(self):
        outsider = User.objects.create_user(
            username="outsider", phone_number="+15552222222", password="testpass123"
        )
        self.client.login(username="outsider", password="testpass123")
        response = self.client.get(self.url)
        assert response.status_code == 403

    def test_not_voting_phase_redirects(self):
        self.round.status = "in_progress"
        self.round.save()
        response = self.client.get(self.url, follow=True)
        assert response.status_code == 200
        assert b"not in voting phase" in response.content

    def test_voting_view_loads(self):
        response = self.client.get(self.url)
        assert response.status_code == 200
        self.assertTemplateUsed(response, "discussions/voting.html")
        assert "mrl_decrease" in response.context
        assert "mrl_increase" in response.context
        assert "rtm_decrease" in response.context
        assert "rtm_increase" in response.context
        assert "voting_time_remaining" in response.context


class TestDiscussionObserverView(TestCase):
    """Tests for the observer view."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        self.client.login(username="testuser", password="testpass123")
        self.url = reverse("discussion-observer", kwargs={"discussion_id": self.discussion.id})

    def test_observer_with_mrp_timeout_reason(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="observer",
            observer_reason="mrp_timeout",
        )
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.context["observer_reason"] == "mrp_timeout"

    def test_observer_with_removed_by_vote_reason(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="observer",
            observer_reason="removed_by_vote",
        )
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.context["observer_reason"] == "removed"

    def test_non_participant_viewer(self):
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.context["observer_reason"] == "viewing"

    def test_no_round_redirects(self):
        self.round.delete()
        response = self.client.get(self.url)
        assert response.status_code == 302


class TestDiscussionCreateWizardView(TestCase):
    """Tests for the discussion creation wizard."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_wizard_loads(self):
        response = self.client.get(reverse("discussion-create-wizard"))
        assert response.status_code == 200
        self.assertTemplateUsed(response, "discussions/create_wizard.html")
        assert "max_headline_length" in response.context
        assert "max_topic_length" in response.context


class TestNotificationPreferencesView(TestCase):
    """Tests for the notification preferences view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_get_preferences(self):
        response = self.client.get(reverse("notification-preferences-view"))
        assert response.status_code == 200
        self.assertTemplateUsed(response, "dashboard/notification_preferences.html")
        assert "discussion_prefs" in response.context
        assert "system_prefs" in response.context
        assert "social_prefs" in response.context

    def test_post_preferences(self):
        # Ensure preferences exist first
        from core.services.notification_service import NotificationService
        NotificationService.create_notification_preferences(self.user)

        prefs = NotificationPreference.objects.filter(user=self.user)
        if prefs.exists():
            pref = prefs.first()
            response = self.client.post(
                reverse("notification-preferences-view"),
                {f"pref_{pref.notification_type}_email": "on", f"pref_{pref.notification_type}_in_app": "on"},
            )
            assert response.status_code == 302


class TestNotificationsView(TestCase):
    """Tests for the notifications view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_mark_all_read_get(self):
        response = self.client.get(reverse("notifications"), {"mark_all_read": "true"})
        assert response.status_code == 302

    def test_mark_all_read_post_endpoint(self):
        NotificationLog.objects.create(
            user=self.user, notification_type="test", title="T", message="M"
        )
        response = self.client.post(reverse("mark-all-read"))
        assert response.status_code == 200

    def test_mark_all_read_get_endpoint_error(self):
        response = self.client.get(reverse("mark-all-read"))
        assert response.status_code == 405


class TestUserSettingsView(TestCase):
    """Tests for the user settings view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_post_settings(self):
        response = self.client.post(reverse("user-settings"), {})
        assert response.status_code == 302


class TestAdminViews(TestCase):
    """Tests for admin-only views."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin", phone_number="+15559999999", password="adminpass123",
            is_staff=True,
        )
        self.client.login(username="admin", password="adminpass123")

    def test_admin_config_post(self):
        PlatformConfig.load()
        response = self.client.post(reverse("admin-config"), {})
        assert response.status_code == 302

    def test_admin_analytics(self):
        response = self.client.get(reverse("admin-analytics"))
        assert response.status_code == 200
        assert "analytics" in response.context

    def test_admin_moderation_queue(self):
        response = self.client.get(reverse("admin-moderation-queue"))
        assert response.status_code == 200
        assert "flagged_users" in response.context


class TestDashboardNewView(TestCase):
    """Tests for the new dashboard with discussion state cards."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress",
            start_time=timezone.now()
        )
        self.client.login(username="testuser", password="testpass123")

    def test_active_needs_response_card(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="active"
        )
        response = self.client.get(reverse("dashboard"))
        assert response.status_code == 200
        discussions = response.context["discussions"]
        assert len(discussions) == 1
        assert discussions[0]["ui_status"] == "active-needs-response"

    def test_waiting_card_after_response(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="active"
        )
        Response.objects.create(
            round=self.round, user=self.user, content="My response"
        )
        response = self.client.get(reverse("dashboard"))
        discussions = response.context["discussions"]
        assert discussions[0]["ui_status"] == "waiting"

    def test_voting_available_card(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="active"
        )
        self.round.status = "voting"
        self.round.save()
        response = self.client.get(reverse("dashboard"))
        discussions = response.context["discussions"]
        assert discussions[0]["ui_status"] == "voting-available"

    def test_observer_card(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="observer"
        )
        response = self.client.get(reverse("dashboard"))
        discussions = response.context["discussions"]
        assert discussions[0]["ui_status"] == "observer"


class TestDetailViewRouting(TestCase):
    """Tests for the discussion detail view routing logic."""

    def setUp(self):
        config = PlatformConfig.load()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", phone_number="+15551111111", password="testpass123"
        )
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Details",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes,
        )
        self.round = Round.objects.create(
            discussion=self.discussion, round_number=1, status="in_progress"
        )
        self.client.login(username="testuser", password="testpass123")
        self.url = reverse("discussion-detail", kwargs={"discussion_id": self.discussion.id})

    def test_active_participant_routes_to_active(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="active"
        )
        response = self.client.get(self.url)
        assert response.status_code == 302
        assert "active" in response.url

    def test_active_participant_in_voting_routes_to_voting(self):
        DiscussionParticipant.objects.create(
            discussion=self.discussion, user=self.user, role="initiator"
        )
        self.round.status = "voting"
        self.round.save()
        response = self.client.get(self.url)
        assert response.status_code == 302
        assert "voting" in response.url

    def test_non_participant_routes_to_observer(self):
        response = self.client.get(self.url)
        assert response.status_code == 302
        assert "observer" in response.url
