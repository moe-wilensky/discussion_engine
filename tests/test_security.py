"""
Tests for security and abuse detection system.

Tests rate limiting, spam detection, and user flagging.
"""

import pytest
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from core.security.abuse_detection import AbuseDetectionService
from core.models import Invite


@pytest.mark.django_db
class TestAbuseDetection:
    """Test abuse detection service."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear cache before each test."""
        cache.clear()

    def test_rate_limit_within_limit(self):
        """Test rate limiting allows requests within limit."""
        identifier = "user_123"
        action = "invite_sends"

        # Should allow first request
        result = AbuseDetectionService.check_rate_limit(identifier, action)
        assert result is True

    def test_rate_limit_exceeded(self):
        """Test rate limiting blocks when limit exceeded."""
        identifier = "user_123"
        action = "invite_sends"

        config = AbuseDetectionService.RATE_LIMITS[action]

        # Exhaust limit
        for _ in range(config["max_requests"]):
            AbuseDetectionService.check_rate_limit(identifier, action)

        # Next request should be blocked
        result = AbuseDetectionService.check_rate_limit(identifier, action)
        assert result is False

    def test_rate_limit_remaining(self):
        """Test getting remaining requests."""
        identifier = "user_123"
        action = "invite_sends"

        # Initial remaining
        remaining = AbuseDetectionService.get_rate_limit_remaining(identifier, action)
        config = AbuseDetectionService.RATE_LIMITS[action]
        assert remaining == config["max_requests"]

        # After one request
        AbuseDetectionService.check_rate_limit(identifier, action)
        remaining = AbuseDetectionService.get_rate_limit_remaining(identifier, action)
        assert remaining == config["max_requests"] - 1

    def test_detect_spam_excessive_invites(self, user_factory):
        """Test spam detection for excessive invites."""
        user = user_factory()

        # Create many recent invites
        for _ in range(25):
            Invite.objects.create(inviter=user, invite_type="platform", status="sent")

        result = AbuseDetectionService.detect_spam_pattern(user)

        assert "excessive_invites_24h" in result["flags"]
        assert result["confidence"] > 0

    def test_detect_spam_high_decline_rate(self, user_factory):
        """Test spam detection for high decline rate."""
        user = user_factory()

        # Create invites with high decline rate
        for _ in range(10):
            Invite.objects.create(
                inviter=user, invite_type="platform", status="declined"
            )

        for _ in range(2):
            Invite.objects.create(
                inviter=user, invite_type="platform", status="accepted"
            )

        result = AbuseDetectionService.detect_spam_pattern(user)

        assert "high_decline_rate" in result["flags"]
        assert result["confidence"] > 0

    def test_detect_spam_no_participation(self, user_factory):
        """Test spam detection for no actual participation."""
        user = user_factory()

        # User sent invites but has no responses
        for _ in range(5):
            Invite.objects.create(inviter=user, invite_type="platform", status="sent")

        result = AbuseDetectionService.detect_spam_pattern(user)

        assert "no_participation" in result["flags"]

    def test_detect_spam_invite_formula_violation(self, user_factory):
        """Test spam detection for invite formula violation."""
        user = user_factory()

        # Violate formula: acquired should equal used + banked
        user.platform_invites_acquired = 10
        user.platform_invites_used = 3
        user.platform_invites_banked = 5  # Should be 7
        user.save()

        result = AbuseDetectionService.detect_spam_pattern(user)

        assert "invite_formula_violation_platform" in result["flags"]
        assert result["confidence"] > 0.7
        assert result["is_spam"] is True

    def test_detect_spam_new_account_spam(self, user_factory):
        """Test spam detection for new account spam."""
        user = user_factory()

        # Create many invites from new account
        for _ in range(10):
            Invite.objects.create(inviter=user, invite_type="platform", status="sent")

        result = AbuseDetectionService.detect_spam_pattern(user)

        # New account with many invites should be flagged
        assert result["confidence"] > 0

    def test_flag_for_review(self, user_factory):
        """Test flagging user for admin review."""
        user = user_factory()

        AbuseDetectionService.flag_for_review(user, "Suspicious behavior")

        user.refresh_from_db()
        assert "admin_flags" in user.behavioral_flags
        assert len(user.behavioral_flags["admin_flags"]) == 1
        assert (
            user.behavioral_flags["admin_flags"][0]["reason"] == "Suspicious behavior"
        )
        assert user.behavioral_flags["admin_flags"][0]["resolved"] is False

    def test_is_flagged(self, user_factory):
        """Test checking if user is flagged."""
        user = user_factory()

        assert not AbuseDetectionService.is_flagged(user)

        AbuseDetectionService.flag_for_review(user, "Test")

        assert AbuseDetectionService.is_flagged(user)

    def test_clean_user_not_spam(self, user_factory, response_factory):
        """Test clean user is not flagged as spam."""
        user = user_factory()

        # Normal behavior: some responses, some invites
        for _ in range(10):
            response_factory(user=user)

        Invite.objects.create(inviter=user, invite_type="platform", status="sent")
        Invite.objects.create(inviter=user, invite_type="platform", status="accepted")

        # Set valid invite counts
        user.platform_invites_acquired = 2
        user.platform_invites_used = 1
        user.platform_invites_banked = 1
        user.save()

        result = AbuseDetectionService.detect_spam_pattern(user)

        assert result["is_spam"] is False
        assert result["confidence"] < 0.7
