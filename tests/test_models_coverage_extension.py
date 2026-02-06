"""
Coverage extension tests for core/models.py.

Created to achieve 85%+ coverage. Tests focus on uncovered code paths,
edge cases, and error handling in model methods.
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import (
    User,
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    Invite,
    JoinRequest,
    JoinRequestVote,
    RemovalVote,
    Vote,
)
from tests.factories import UserFactory, DiscussionFactory


class UserModelCoverageTests(TestCase):
    """Extend coverage for User model methods."""

    def setUp(self):
        self.user = UserFactory()

    def test_can_send_platform_invite_with_zero_banked(self):
        """Test can_send_platform_invite returns False with 0 banked invites."""
        self.user.platform_invites_banked = 0
        self.user.save()

        self.assertFalse(self.user.can_send_platform_invite())

    def test_can_send_platform_invite_with_nonzero_banked(self):
        """Test can_send_platform_invite returns True with >0 banked invites."""
        self.user.platform_invites_banked = 5
        self.user.save()

        self.assertTrue(self.user.can_send_platform_invite())

    def test_can_send_discussion_invite_with_zero_banked(self):
        """Test can_send_discussion_invite returns False with 0 banked invites."""
        self.user.discussion_invites_banked = 0
        self.user.save()

        self.assertFalse(self.user.can_send_discussion_invite())

    def test_can_send_discussion_invite_with_nonzero_banked(self):
        """Test can_send_discussion_invite returns True with >0 banked invites."""
        self.user.discussion_invites_banked = 25
        self.user.save()

        self.assertTrue(self.user.can_send_discussion_invite())

    def test_earn_invite_platform_type(self):
        """Test earn_invite correctly awards platform invites."""
        initial_acquired = self.user.platform_invites_acquired
        initial_banked = self.user.platform_invites_banked

        self.user.earn_invite('platform')

        self.user.refresh_from_db()
        self.assertEqual(self.user.platform_invites_acquired, initial_acquired + 1)
        self.assertEqual(self.user.platform_invites_banked, initial_banked + 1)

    def test_earn_invite_discussion_type(self):
        """Test earn_invite correctly awards discussion invites."""
        initial_acquired = self.user.discussion_invites_acquired
        initial_banked = self.user.discussion_invites_banked

        self.user.earn_invite('discussion')

        self.user.refresh_from_db()
        self.assertEqual(self.user.discussion_invites_acquired, initial_acquired + 1)
        self.assertEqual(self.user.discussion_invites_banked, initial_banked + 1)

    def test_earn_invite_invalid_type_raises_error(self):
        """Test earn_invite raises ValueError for invalid invite type."""
        with self.assertRaises(ValueError) as context:
            self.user.earn_invite('invalid_type')

        self.assertIn('Invalid invite_type', str(context.exception))

    def test_consume_invite_platform_type(self):
        """Test consume_invite correctly consumes platform invites."""
        self.user.platform_invites_banked = 5
        self.user.platform_invites_used = 2
        self.user.save()

        self.user.consume_invite('platform')

        self.user.refresh_from_db()
        self.assertEqual(self.user.platform_invites_banked, 4)
        self.assertEqual(self.user.platform_invites_used, 3)

    def test_consume_invite_discussion_type(self):
        """Test consume_invite correctly consumes discussion invites."""
        self.user.discussion_invites_banked = 10
        self.user.discussion_invites_used = 1
        self.user.save()

        self.user.consume_invite('discussion')

        self.user.refresh_from_db()
        self.assertEqual(self.user.discussion_invites_banked, 9)
        self.assertEqual(self.user.discussion_invites_used, 2)

    def test_consume_invite_platform_no_banked_raises_error(self):
        """Test consume_invite raises ValidationError when no platform invites available."""
        self.user.platform_invites_banked = 0
        self.user.save()

        with self.assertRaises(ValidationError) as context:
            self.user.consume_invite('platform')

        self.assertIn('No platform invites available', str(context.exception))

    def test_consume_invite_discussion_no_banked_raises_error(self):
        """Test consume_invite raises ValidationError when no discussion invites available."""
        self.user.discussion_invites_banked = 0
        self.user.save()

        with self.assertRaises(ValidationError) as context:
            self.user.consume_invite('discussion')

        self.assertIn('No discussion invites available', str(context.exception))

    def test_consume_invite_invalid_type_raises_error(self):
        """Test consume_invite raises ValueError for invalid invite type."""
        with self.assertRaises(ValueError) as context:
            self.user.consume_invite('invalid')

        self.assertIn('Invalid invite_type', str(context.exception))


class DiscussionParticipantObserverCoverageTests(TestCase):
    """Extend coverage for DiscussionParticipant observer reintegration methods."""

    def setUp(self):
        self.user = UserFactory()
        self.discussion = DiscussionFactory(initiator=self.user)
        # DiscussionFactory auto-creates participant for initiator
        self.participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.user
        )

    def test_can_rejoin_returns_false_for_active_participant(self):
        """Test can_rejoin returns False for active participants."""
        self.participant.role = 'active'
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_returns_false_when_no_current_round(self):
        """Test can_rejoin returns False when there's no in-progress round."""
        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now()
        self.participant.observer_reason = 'mrp_expired'
        self.participant.save()

        # No rounds exist
        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_returns_false_when_observer_since_is_none(self):
        """Test can_rejoin returns False when observer_since is None."""
        self.participant.role = 'temporary_observer'
        self.participant.observer_since = None
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_mrp_expired_posted_in_round_true(self):
        """Test can_rejoin for MRP expiration with posting returns True."""
        # Create removal round
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        # Create current round
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now() - timedelta(hours=1)
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        self.assertTrue(self.participant.can_rejoin())

    def test_can_rejoin_mrp_expired_not_posted_next_round(self):
        """Test can_rejoin for MRP expiration without posting in next round."""
        # Create removal round
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        # Create current round (next round)
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        self.assertTrue(self.participant.can_rejoin())

    def test_can_rejoin_mrp_expired_not_posted_same_round(self):
        """Test can_rejoin for MRP expiration without posting in same round returns False."""
        # Create removal round (current round)
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=1),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_mutual_removal_posted_can_rejoin_round_n_plus_2(self):
        """Test can_rejoin for mutual removal with posting can rejoin in round N+2."""
        # Create removal round (round 1)
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=4),
            status='completed'
        )

        # Create round 2 (must skip this)
        round_2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        # Create current round (round 3 - can rejoin)
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=3,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        self.assertTrue(self.participant.can_rejoin())

    def test_can_rejoin_mutual_removal_posted_cannot_rejoin_round_n_plus_1(self):
        """Test can_rejoin for mutual removal with posting cannot rejoin in round N+1."""
        # Create removal round (round 1)
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        # Create current round (round 2 - must skip this)
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_mutual_removal_not_posted_can_rejoin_next_round(self):
        """Test can_rejoin for mutual removal without posting can rejoin in next round."""
        # Create removal round
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        # Create current round (next round)
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        self.assertTrue(self.participant.can_rejoin())

    def test_can_rejoin_mutual_removal_not_posted_cannot_rejoin_same_round(self):
        """Test can_rejoin for mutual removal without posting cannot rejoin same round."""
        # Create removal round (current round)
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=1),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_vote_based_removal_returns_false(self):
        """Test can_rejoin for vote-based removal always returns False (permanent)."""
        # Create rounds
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now() - timedelta(hours=1)
        self.participant.observer_reason = 'vote_based_removal'
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_can_rejoin_returns_false_when_no_removal_round_found(self):
        """Test can_rejoin returns False when removal round cannot be found."""
        # Create current round but with start_time after observer_since
        current_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() + timedelta(hours=1),  # After observer_since
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now()
        self.participant.observer_reason = 'mrp_expired'
        self.participant.save()

        self.assertFalse(self.participant.can_rejoin())

    def test_get_wait_period_end_returns_none_for_active_participant(self):
        """Test get_wait_period_end returns None for active participants."""
        self.participant.role = 'active'
        self.participant.save()

        self.assertIsNone(self.participant.get_wait_period_end())

    def test_get_wait_period_end_returns_none_when_observer_since_is_none(self):
        """Test get_wait_period_end returns None when observer_since is None."""
        self.participant.role = 'temporary_observer'
        self.participant.observer_since = None
        self.participant.save()

        self.assertIsNone(self.participant.get_wait_period_end())

    def test_get_wait_period_end_returns_none_when_no_removal_round(self):
        """Test get_wait_period_end returns None when no removal round found."""
        # Create round after observer_since
        Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() + timedelta(hours=1),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now()
        self.participant.observer_reason = 'mrp_expired'
        self.participant.save()

        self.assertIsNone(self.participant.get_wait_period_end())

    def test_get_wait_period_end_mrp_expired_posted_returns_observer_since(self):
        """Test get_wait_period_end for MRP with posting returns observer_since."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        observer_since = timezone.now() - timedelta(hours=1)
        self.participant.role = 'temporary_observer'
        self.participant.observer_since = observer_since
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertEqual(wait_end, observer_since)

    def test_get_wait_period_end_mrp_expired_not_posted_returns_next_round_start(self):
        """Test get_wait_period_end for MRP without posting returns next round start."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        next_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertEqual(wait_end, next_round.start_time)

    def test_get_wait_period_end_mrp_expired_not_posted_no_next_round_returns_approximation(self):
        """Test get_wait_period_end for MRP without posting with no next round returns approximation."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.role = 'temporary_observer'
        self.participant.observer_since = observer_since
        self.participant.observer_reason = 'mrp_expired'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        expected = observer_since + timedelta(hours=24)
        self.assertEqual(wait_end, expected)

    def test_get_wait_period_end_mutual_removal_posted_returns_round_n_plus_2_start(self):
        """Test get_wait_period_end for mutual removal with posting returns round N+2 start."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=4),
            status='completed'
        )

        round_2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        rejoin_round = Round.objects.create(
            discussion=self.discussion,
            round_number=3,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertEqual(wait_end, rejoin_round.start_time)

    def test_get_wait_period_end_mutual_removal_posted_no_rejoin_round_returns_none(self):
        """Test get_wait_period_end for mutual removal with posting but no round N+2 returns None."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = True
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertIsNone(wait_end)

    def test_get_wait_period_end_mutual_removal_not_posted_returns_next_round_start(self):
        """Test get_wait_period_end for mutual removal without posting returns next round start."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        next_round = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            start_time=timezone.now(),
            status='in_progress'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertEqual(wait_end, next_round.start_time)

    def test_get_wait_period_end_mutual_removal_not_posted_no_next_round_returns_none(self):
        """Test get_wait_period_end for mutual removal without posting but no next round returns None."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = removal_round.start_time + timedelta(minutes=30)
        self.participant.observer_reason = 'mutual_removal'
        self.participant.posted_in_round_when_removed = False
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertIsNone(wait_end)

    def test_get_wait_period_end_unknown_reason_returns_none(self):
        """Test get_wait_period_end for unknown observer reason returns None."""
        removal_round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            start_time=timezone.now() - timedelta(hours=2),
            status='completed'
        )

        self.participant.role = 'temporary_observer'
        self.participant.observer_since = timezone.now() - timedelta(hours=1)
        self.participant.observer_reason = 'unknown_reason'
        self.participant.save()

        wait_end = self.participant.get_wait_period_end()
        self.assertIsNone(wait_end)


class UserBanModelCoverageTests(TestCase):
    """Extend coverage for User.is_banned() method."""

    def setUp(self):
        self.user = UserFactory()

    def test_is_banned_returns_false_when_no_bans(self):
        """Test is_banned returns False when user has no bans."""
        from core.models import UserBan

        # Ensure no bans
        UserBan.objects.filter(user=self.user).delete()

        self.assertFalse(self.user.is_banned())

    def test_is_banned_returns_true_when_active_ban_exists(self):
        """Test is_banned returns True when active ban exists."""
        from core.models import UserBan

        # Create active ban
        ban = UserBan.objects.create(
            user=self.user,
            banned_by=UserFactory(),
            reason='Test ban',
            is_permanent=False,
            duration_days=1,
            expires_at=timezone.now() + timedelta(days=1),
            is_active=True
        )

        self.assertTrue(self.user.is_banned())

    def test_user_str_method(self):
        """Test User __str__ method returns username and phone."""
        self.user.username = 'testuser'
        self.user.phone_number = '+1234567890'
        self.user.save()

        expected = 'testuser (+1234567890)'
        self.assertEqual(str(self.user), expected)


