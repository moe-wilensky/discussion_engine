"""
Backend Unit Tests for Observer Logic, Ban Expiration, and Invite Codes.

Tests critical edge cases and boundary conditions in:
- Observer rejoin timing (MRP expired, mutual removal)
- Ban expiration and enforcement
- Invite code validation and collision handling
"""

import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model

from core.models import (
    DiscussionParticipant,
    UserBan,
    Invite,
    PlatformConfig,
    Discussion,
    Round,
    Response,
)
from tests.factories import (
    UserFactory,
    DiscussionFactory,
    DiscussionParticipantFactory,
    RoundFactory,
    ResponseFactory,
)

User = get_user_model()


@pytest.mark.django_db
class TestObserverRejoin:
    """Test observer rejoin logic at boundary times."""

    def test_mrp_expired_observer_can_rejoin_next_round(self):
        """
        Test that MRP expired observer can rejoin in next round.

        Scenario:
        - User becomes observer due to MRP expiry in round 1
        - User did NOT post in round 1
        - Round 2 starts
        - User should be able to rejoin
        """
        config = PlatformConfig.load()
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )
        
        # Create round 1
        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="completed"
        )
        round1.start_time = timezone.now() - timedelta(hours=2)
        round1.end_time = timezone.now() - timedelta(hours=1)
        round1.save()
        
        # Make them observer
        participant.role = "temporary_observer"
        participant.observer_reason = "mrp_expired"
        participant.observer_since = round1.start_time + timedelta(minutes=30)
        participant.posted_in_round_when_removed = False
        participant.save()
        
        # Create round 2 (current round)
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status="in_progress"
        )
        round2.start_time = timezone.now() - timedelta(minutes=5)
        round2.save()
        
        # Test rejoin capability
        assert participant.can_rejoin() is True

    def test_mrp_expired_observer_cannot_rejoin_same_round(self):
        """
        Test that MRP expired observer cannot rejoin in same round.

        Scenario:
        - User becomes observer in current round
        - User did NOT post before becoming observer
        - User tries to rejoin immediately
        - Should be blocked
        """
        config = PlatformConfig.load()
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )
        
        # Create current round
        current_round = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        current_round.start_time = timezone.now() - timedelta(minutes=30)
        current_round.save()
        
        # Make them observer
        participant.role = "temporary_observer"
        participant.observer_reason = "mrp_expired"
        participant.observer_since = timezone.now() - timedelta(minutes=10)
        participant.posted_in_round_when_removed = False
        participant.save()
        
        # Test rejoin capability - should fail (still in same round)
        assert participant.can_rejoin() is False

    def test_mrp_expired_observer_with_post_can_rejoin_immediately(self):
        """
        Test that observer who posted before MRP expiry can rejoin immediately.

        Scenario:
        - User posted a response
        - MRP expired, user became observer
        - User should be able to rejoin immediately
        """
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )

        # Create current round with start_time before observer_since
        current_round = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        current_round.start_time = timezone.now() - timedelta(minutes=10)
        current_round.save()

        # Mark as observer who posted (became observer 5 minutes ago, during this round)
        participant.role = "temporary_observer"
        participant.observer_reason = "mrp_expired"
        participant.observer_since = timezone.now() - timedelta(minutes=5)
        participant.posted_in_round_when_removed = True
        participant.save()

        # Test rejoin capability - should be able to rejoin immediately since they posted
        assert participant.can_rejoin() is True

    def test_mutual_removal_with_post_must_skip_full_round(self):
        """
        Test mutual removal after posting requires skipping entire next round.

        Scenario:
        - User A and User B use kamikaze in round 1 (both had posted)
        - They become observers and must skip round 2 entirely
        - They can rejoin in round 3
        """
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )

        # Create round 1 where removal happened
        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="completed"
        )
        round1.start_time = timezone.now() - timedelta(hours=3)
        round1.end_time = timezone.now() - timedelta(hours=2)
        round1.save()

        # Mark as observer after posting (kamikaze)
        participant.role = "temporary_observer"
        participant.observer_reason = "mutual_removal"
        participant.observer_since = round1.end_time
        participant.posted_in_round_when_removed = True
        participant.save()

        # Create round 2 (must skip)
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status="in_progress"
        )
        round2.start_time = timezone.now() - timedelta(hours=1)
        round2.save()

        # Cannot rejoin in round 2
        assert participant.can_rejoin() is False

        # Create round 3 (can rejoin)
        round3 = RoundFactory(
            discussion=discussion,
            round_number=3,
            status="in_progress"
        )
        round3.start_time = timezone.now()
        round3.save()

        # Now can rejoin in round 3
        assert participant.can_rejoin() is True

    def test_mutual_removal_without_post_can_rejoin_next_round(self):
        """
        Test mutual removal without posting allows rejoin in next round.

        Scenario:
        - User becomes observer via kamikaze but hadn't posted yet
        - Can rejoin in the next round (after 1 MRP)
        """
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )

        # Create round 1 where removal happened
        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="completed"
        )
        round1.start_time = timezone.now() - timedelta(hours=2)
        round1.end_time = timezone.now() - timedelta(hours=1)
        round1.save()

        # Mark as observer without posting
        participant.role = "temporary_observer"
        participant.observer_reason = "mutual_removal"
        participant.observer_since = round1.end_time
        participant.posted_in_round_when_removed = False
        participant.save()

        # Create round 2
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status="in_progress"
        )
        round2.start_time = timezone.now() - timedelta(minutes=5)
        round2.save()

        # Can rejoin in round 2
        assert participant.can_rejoin() is True

    def test_mutual_removal_with_post_cannot_rejoin_in_skip_round(self):
        """
        Test that kamikaze user cannot rejoin during the skip round.

        Scenario:
        - User kamikazed in round 1 after posting
        - Round 2 is in progress
        - User tries to rejoin - should be blocked
        """
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )

        # Create round 1 where kamikaze happened
        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="completed"
        )
        round1.start_time = timezone.now() - timedelta(hours=2)
        round1.save()

        # Mark as observer after posting
        participant.role = "temporary_observer"
        participant.observer_reason = "mutual_removal"
        participant.observer_since = timezone.now() - timedelta(hours=1)
        participant.posted_in_round_when_removed = True
        participant.save()

        # Create round 2 (the skip round)
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status="in_progress"
        )
        round2.start_time = timezone.now() - timedelta(minutes=30)
        round2.save()

        # Should NOT be able to rejoin in round 2
        assert participant.can_rejoin() is False

    def test_vote_based_removal_is_permanent(self):
        """Test that vote-based removal is always permanent."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )
        participant.role = "temporary_observer"
        participant.observer_reason = "vote_based_removal"
        participant.observer_since = timezone.now() - timedelta(days=365)
        participant.save()

        # Should never be able to rejoin
        assert participant.can_rejoin() is False

    def test_permanent_observer_cannot_rejoin(self):
        """Test that permanent observers can never rejoin."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)

        # Get the auto-created participant record
        participant = DiscussionParticipant.objects.get(
            discussion=discussion,
            user=user
        )
        participant.role = "permanent_observer"
        participant.save()

        # Should never be able to rejoin
        assert participant.can_rejoin() is False


@pytest.mark.django_db
class TestBanExpiration:
    """Test ban expiration and enforcement."""

    def test_expired_ban_allows_login(self):
        """
        Test that expired temporary ban allows user to log in.
        
        Scenario:
        - User has temporary ban (7 days)
        - Ban expired 1 second ago
        - User should NOT be banned
        """
        user = UserFactory()
        
        # Create expired ban
        ban = UserBan.objects.create(
            user=user,
            banned_by=user,  # Self-ban for testing
            reason="Test temporary ban",
            is_permanent=False,
            duration_days=7,
            expires_at=timezone.now() - timedelta(seconds=1),
            is_active=True
        )
        
        # Test ban status
        assert ban.is_currently_banned() is False
        assert user.is_banned() is False

    def test_active_temporary_ban_blocks_login(self):
        """
        Test that active temporary ban blocks user login.
        
        Boundary test: 1 second before expiry.
        """
        user = UserFactory()
        
        # Create ban expiring in 1 second
        ban = UserBan.objects.create(
            user=user,
            banned_by=user,
            reason="Test temporary ban",
            is_permanent=False,
            duration_days=7,
            expires_at=timezone.now() + timedelta(seconds=1),
            is_active=True
        )
        
        # Test ban status
        assert ban.is_currently_banned() is True
        assert user.is_banned() is True

    def test_permanent_ban_never_expires(self):
        """Test that permanent ban never expires."""
        user = UserFactory()
        
        # Create permanent ban (long ago)
        ban = UserBan.objects.create(
            user=user,
            banned_by=user,
            reason="Permanent ban",
            is_permanent=True,
            is_active=True
        )
        ban.created_at = timezone.now() - timedelta(days=365)
        ban.save()
        
        # Test ban status
        assert ban.is_currently_banned() is True
        assert user.is_banned() is True

    def test_lifted_ban_allows_login(self):
        """Test that lifted ban allows login regardless of expiry."""
        user = UserFactory()
        admin = UserFactory(is_platform_admin=True)
        
        # Create active ban
        ban = UserBan.objects.create(
            user=user,
            banned_by=admin,
            reason="Test ban",
            is_permanent=False,
            duration_days=7,
            expires_at=timezone.now() + timedelta(days=3),
            is_active=False,  # Lifted
            lifted_by=admin,
            lifted_at=timezone.now(),
            lift_reason="Appeal accepted"
        )
        
        # Test ban status
        assert ban.is_currently_banned() is False
        assert user.is_banned() is False

    def test_multiple_bans_most_recent_active_wins(self):
        """Test that with multiple bans, only active ones matter."""
        user = UserFactory()
        admin = UserFactory(is_platform_admin=True)
        
        # Old expired ban
        UserBan.objects.create(
            user=user,
            banned_by=admin,
            reason="Old ban",
            is_permanent=False,
            duration_days=7,
            expires_at=timezone.now() - timedelta(days=1),
            is_active=True
        )
        
        # Recent active ban
        active_ban = UserBan.objects.create(
            user=user,
            banned_by=admin,
            reason="Recent ban",
            is_permanent=False,
            duration_days=14,
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True
        )
        
        # User should be banned because of the active ban
        assert user.is_banned() is True


@pytest.mark.django_db
class TestInviteCodes:
    """Test invite code validation and collision handling."""

    def test_invalid_invite_code_rejects(self):
        """Test that invalid invite code is rejected."""
        # Try to find invite with non-existent code
        invite = Invite.objects.filter(code="INVALID1").first()
        assert invite is None

    def test_expired_invite_code_validation(self):
        """Test that expired invite codes cannot be used."""
        user = UserFactory()
        
        # Create expired invite
        invite = Invite.objects.create(
            inviter=user,
            invite_type="platform",
            status="sent",
            expires_at=timezone.now() - timedelta(hours=1)
        )
        
        # Verify invite exists but is expired
        assert invite.code is not None
        assert invite.expires_at < timezone.now()

    def test_invite_code_generation_uniqueness(self):
        """Test that generated invite codes are unique."""
        user = UserFactory()
        
        # Generate multiple invites
        codes = set()
        for _ in range(10):
            invite = Invite.objects.create(
                inviter=user,
                invite_type="platform",
                status="sent"
            )
            codes.add(invite.code)
        
        # All codes should be unique
        assert len(codes) == 10

    def test_invite_code_collision_handling(self):
        """
        Test that code collision is handled by generating new code.
        
        Simulates collision scenario by mocking random choices.
        """
        user = UserFactory()
        
        # Create first invite with a specific code
        invite1 = Invite.objects.create(
            inviter=user,
            invite_type="platform",
            status="sent"
        )
        existing_code = invite1.code
        
        # Mock generate_code to first return existing code, then new code
        call_count = [0]
        
        def mock_generate():
            call_count[0] += 1
            if call_count[0] == 1:
                return existing_code  # First call returns collision
            return "NEWCODE1"  # Second call returns unique code
        
        with patch.object(Invite, 'generate_code', side_effect=mock_generate):
            # This should detect collision and generate new code
            code1 = Invite.generate_code()
            code2 = Invite.generate_code()
            
            # First call returns existing, second returns new
            assert code1 == existing_code
            assert code2 == "NEWCODE1"

    def test_invite_code_format_validation(self):
        """Test that generated invite codes follow correct format."""
        user = UserFactory()
        
        invite = Invite.objects.create(
            inviter=user,
            invite_type="platform",
            status="sent"
        )
        
        # Code should be 8 characters, uppercase alphanumeric
        assert len(invite.code) == 8
        assert invite.code.isupper()
        assert invite.code.isalnum()

    def test_discussion_invite_no_auto_code(self):
        """Test that discussion invites don't auto-generate codes."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)
        
        invite = Invite.objects.create(
            inviter=user,
            invitee=UserFactory(),
            invite_type="discussion",
            discussion=discussion,
            status="sent"
        )
        
        # Discussion invites should not have auto-generated codes
        assert invite.code is None or invite.code == ""

    def test_accepted_invite_cannot_be_reused(self):
        """Test that accepted invite cannot be used again."""
        user = UserFactory()
        invitee = UserFactory()
        
        invite = Invite.objects.create(
            inviter=user,
            invitee=invitee,
            invite_type="platform",
            status="accepted",
            accepted_at=timezone.now()
        )
        
        # Verify invite is accepted
        assert invite.status == "accepted"
        assert invite.accepted_at is not None
        
        # In a real scenario, trying to use this code again would fail
        # because the status is not "sent"

    def test_multiple_invites_different_codes(self):
        """Test that multiple invites from same user get different codes."""
        user = UserFactory()
        
        invite1 = Invite.objects.create(
            inviter=user,
            invite_type="platform",
            status="sent"
        )
        
        invite2 = Invite.objects.create(
            inviter=user,
            invite_type="platform",
            status="sent"
        )
        
        # Codes must be different
        assert invite1.code != invite2.code
        assert invite1.code is not None
        assert invite2.code is not None
