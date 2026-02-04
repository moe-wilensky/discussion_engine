"""
Pytest configuration and fixtures for testing.
"""

import pytest
from django.contrib.auth import get_user_model
from core.models import PlatformConfig

User = get_user_model()


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Set up test database with initial config."""
    with django_db_blocker.unblock():
        PlatformConfig.load()


@pytest.fixture
def config():
    """Provide PlatformConfig instance."""
    return PlatformConfig.load()


@pytest.fixture
def user_factory(db):
    """Factory for creating users."""
    counter = {"value": 0}

    def create_user(username=None, phone_number=None, **kwargs):
        import time

        counter["value"] += 1
        if not username:
            username = f'user_{counter["value"]}_{int(time.time() * 1000000)}'
        if not phone_number:
            phone_number = f'+1555{counter["value"]:010d}'

        return User.objects.create_user(
            username=username,
            phone_number=phone_number,
            password="testpass123",
            **kwargs,
        )

    return create_user


@pytest.fixture
def user(user_factory):
    """Provide a single test user."""
    return user_factory()


@pytest.fixture
def discussion_factory(db, user_factory, config):
    """Factory for creating discussions."""
    from core.models import Discussion, DiscussionParticipant

    def create_discussion(initiator=None, **kwargs):
        if not initiator:
            initiator = user_factory()

        defaults = {
            "topic_headline": "Test Discussion",
            "topic_details": "This is a test discussion topic.",
            "max_response_length_chars": config.mrl_min_chars,
            "response_time_multiplier": 1.0,
            "min_response_time_minutes": config.mrm_min_minutes,
        }
        defaults.update(kwargs)

        discussion = Discussion.objects.create(initiator=initiator, **defaults)

        # Create participant record for initiator
        DiscussionParticipant.objects.create(
            discussion=discussion, user=initiator, role="initiator"
        )

        return discussion

    return create_discussion


@pytest.fixture
def discussion(discussion_factory):
    """Provide a single test discussion."""
    return discussion_factory()


@pytest.fixture
def round_factory(db, discussion_factory):
    """Factory for creating rounds."""
    from core.models import Round

    def create_round(discussion=None, round_number=None, **kwargs):
        if not discussion:
            discussion = discussion_factory()

        if round_number is None:
            # Get next round number
            last_round = discussion.rounds.order_by("-round_number").first()
            round_number = (last_round.round_number + 1) if last_round else 1

        return Round.objects.create(
            discussion=discussion, round_number=round_number, **kwargs
        )

    return create_round


@pytest.fixture
def response_factory(db, user_factory, discussion_factory):
    """Factory for creating responses."""
    from core.models import Response, Round, DiscussionParticipant

    def create_response(user=None, discussion=None, **kwargs):
        if not user:
            user = user_factory()

        if not discussion:
            discussion = discussion_factory()

        # Ensure user is participant
        if not DiscussionParticipant.objects.filter(
            discussion=discussion, user=user
        ).exists():
            DiscussionParticipant.objects.create(
                discussion=discussion, user=user, role="active"
            )

        # Get or create a round
        round_obj = discussion.rounds.first()
        if not round_obj:
            round_obj = Round.objects.create(
                discussion=discussion, round_number=1, status="in_progress"
            )

        defaults = {
            "content": "Test response content that is long enough to meet minimum requirements.",
        }
        defaults.update(kwargs)

        return Response.objects.create(user=user, round=round_obj, **defaults)

    return create_response


@pytest.fixture
def api_client():
    """Provide unauthenticated API client."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def authenticated_client(user_factory):
    """Provide authenticated API client with user."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    user = user_factory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    client.user = user

    return client


# Playwright configuration for Django integration
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for Playwright tests."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
    }
