"""
Unit tests for InviteService.

Tests the validate_code and consume_code methods.
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models import User, Invite, PlatformConfig
from core.services.invite_service import InviteService


@pytest.mark.django_db
class TestInviteCodeValidation:
    """Test invite code validation logic."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)

    def test_validate_code_success(self, user_factory):
        """Test that valid invite code passes validation."""
        inviter = user_factory()

        # Create invite with explicit code
        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="platform",
            status="sent"
        )

        # Validate should succeed
        validated_invite = InviteService.validate_code(invite.code)
        assert validated_invite.id == invite.id
        assert validated_invite.status == "sent"

    def test_validate_code_invalid_code(self):
        """Test that invalid invite code raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid invite code"):
            InviteService.validate_code("INVALID123")

    def test_validate_code_already_used(self, user_factory):
        """Test that already accepted invite raises ValidationError."""
        inviter = user_factory()

        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="platform",
            status="accepted"  # Already used
        )

        with pytest.raises(ValidationError, match="already been used"):
            InviteService.validate_code(invite.code)

    def test_validate_code_wrong_type(self, user_factory, discussion_factory):
        """Test that discussion invite raises ValidationError."""
        inviter = user_factory()
        discussion = discussion_factory(initiator=inviter)

        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="discussion",  # Wrong type
            discussion=discussion,
            status="sent"
        )

        with pytest.raises(ValidationError, match="Invalid invite type"):
            InviteService.validate_code(invite.code)

    def test_validate_code_expired(self, user_factory):
        """Test that expired invite raises ValidationError."""
        inviter = user_factory()

        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="platform",
            status="sent",
            expires_at=timezone.now() - timedelta(days=1)  # Expired
        )

        with pytest.raises(ValidationError, match="expired"):
            InviteService.validate_code(invite.code)

        # Verify invite was marked as expired
        invite.refresh_from_db()
        assert invite.status == "expired"

    def test_consume_code_success(self, user_factory):
        """Test that consume_code validates and accepts invite."""
        inviter = user_factory()
        invitee = user_factory()

        # Give inviter some banked invites (needed for consumption)
        inviter.platform_invites_banked = 5
        inviter.save()

        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="platform",
            status="sent"
        )

        # Consume the code
        result = InviteService.consume_code(invite.code, invitee)

        # Verify invite was accepted
        invite.refresh_from_db()
        assert invite.status == "accepted"
        assert invite.invitee == invitee

    def test_generate_code_creates_unique_codes(self, user_factory):
        """Test that generate_code creates unique codes."""
        inviter = user_factory()

        # Create multiple invites
        codes = set()
        for _ in range(10):
            invite = Invite.objects.create(
                inviter=inviter,
                invite_type="platform",
                status="sent"
            )
            codes.add(invite.code)

        # All codes should be unique
        assert len(codes) == 10

        # All codes should be 8 characters
        for code in codes:
            assert len(code) == 8
            assert code.isupper()

    def test_get_invite_by_code(self, user_factory):
        """Test get_invite_by_code returns correct invite."""
        inviter = user_factory()

        invite = Invite.objects.create(
            inviter=inviter,
            invite_type="platform",
            status="sent"
        )

        # Should find the invite
        found_invite = InviteService.get_invite_by_code(invite.code)
        assert found_invite.id == invite.id

        # Should return None for non-existent code
        not_found = InviteService.get_invite_by_code("NOTEXIST")
        assert not_found is None
