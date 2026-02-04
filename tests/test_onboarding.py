"""
Tests for onboarding system.

Tests tutorial content, completion tracking, and suggested discussions.
"""

import pytest

from core.services.onboarding import OnboardingService
from core.models import PlatformConfig


@pytest.mark.django_db
class TestOnboardingService:
    """Test onboarding service."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_get_tutorial_steps(self):
        """Test getting tutorial steps."""
        steps = OnboardingService.get_tutorial_steps()

        assert len(steps) > 0
        assert steps[0]["step"] == 1
        assert "title" in steps[0]
        assert "content" in steps[0]

        # Check all steps are sequential
        for i, step in enumerate(steps, 1):
            assert step["step"] == i

    def test_mark_tutorial_complete(self, user_factory):
        """Test marking tutorial as complete."""
        user = user_factory()

        assert not OnboardingService.has_completed_tutorial(user)

        OnboardingService.mark_tutorial_complete(user)

        assert OnboardingService.has_completed_tutorial(user)

        user.refresh_from_db()
        assert "tutorial_completed" in user.behavioral_flags
        assert user.behavioral_flags["tutorial_completed"] is True

    def test_get_suggested_discussions(self, user_factory, discussion_factory):
        """Test getting suggested discussions."""
        user = user_factory()

        # Create active discussions
        active1 = discussion_factory(status="active")
        active2 = discussion_factory(status="active")

        # Create archived discussion
        archived = discussion_factory(status="archived")

        suggestions = OnboardingService.get_suggested_discussions(user)

        # Should include active discussions
        suggestion_ids = [d.id for d in suggestions]
        assert active1.id in suggestion_ids or active2.id in suggestion_ids


@pytest.mark.django_db
class TestOnboardingAPI:
    """Test onboarding API endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_tutorial_endpoint(self, authenticated_client):
        """Test getting tutorial via API."""
        response = authenticated_client.get("/api/onboarding/tutorial/")

        assert response.status_code == 200
        assert len(response.data) > 0
        assert "step" in response.data[0]
        assert "title" in response.data[0]
        assert "content" in response.data[0]

    def test_complete_tutorial_endpoint(self, authenticated_client):
        """Test completing tutorial via API."""
        response = authenticated_client.post("/api/onboarding/tutorial/complete/")

        assert response.status_code == 200
        assert response.data["completed"] is True

        # Check user's flags were updated
        user = authenticated_client.user
        user.refresh_from_db()
        assert user.behavioral_flags.get("tutorial_completed") is True

    def test_suggested_discussions_endpoint(
        self, authenticated_client, discussion_factory
    ):
        """Test suggested discussions endpoint."""
        # Create some discussions
        discussion_factory(status="active")
        discussion_factory(status="active")

        response = authenticated_client.get("/api/onboarding/suggested-discussions/")

        assert response.status_code == 200
        assert isinstance(response.data, list)
