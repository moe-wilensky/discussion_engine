"""
Comprehensive integration tests for ObserverService.

Focus: Achieve 85%+ coverage of observer_service.py
Current: 0% → Target: 85%+

Tests cover all nuanced observer reintegration rules from the mechanics spec.
"""
from decimal import Decimal
from datetime import timedelta
import pytest
from django.test import TransactionTestCase
from django.utils import timezone
from core.models import (
    Discussion, Round, User, DiscussionParticipant,
    PlatformConfig
)
from core.services.observer_service import ObserverService
from tests.factories import UserFactory, DiscussionFactory


class ObserverServiceIntegrationTests(TransactionTestCase):
    """
    Integration tests for ObserverService.

    Tests the complex observer reintegration mechanics including:
    - Moving users to observer status
    - Determining when observers can rejoin
    - Rejoining mechanics
    - Permanent observer status
    """

    def setUp(self):
        """Set up test data with proper constraints."""
        # Get or create platform config
        self.config, _ = PlatformConfig.objects.get_or_create(
            id=1,
            defaults={
                'voting_increment_percentage': 20,
                'mrl_min_chars': 100,
                'mrl_max_chars': 5000,
                'rtm_min': 0.5,
                'rtm_max': 3.0
            }
        )

        # Create users
        self.users = []
        for i in range(5):
            user = UserFactory.create(
                username=f'observer_user{i}',
                email=f'observer_user{i}@test.com',
                platform_invites_acquired=Decimal('10.0'),
                platform_invites_banked=Decimal('10.0'),
                discussion_invites_acquired=50,
                discussion_invites_banked=50
            )
            user.set_password('testpass123')
            user.save()
            self.users.append(user)

        # Create discussion
        self.discussion = DiscussionFactory.create(
            topic_headline='Observer Test Discussion',
            topic_details='Testing observer mechanics',
            initiator=self.users[0],
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30
        )

        # Create participants (users[0] already created by factory)
        for user in self.users[1:4]:
            DiscussionParticipant.objects.create(
                discussion=self.discussion,
                user=user,
                role='active'
            )

        # Create rounds
        self.round1 = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(minutes=60),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

    # Test move_to_observer
    def test_move_to_observer_mrp_expired_no_post(self):
        """Test moving user to observer due to MRP expiration without posting."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        ObserverService.move_to_observer(
            participant,
            reason='mrp_expired',
            posted_in_round=False
        )

        participant.refresh_from_db()
        assert participant.role == 'temporary_observer'
        assert participant.observer_reason == 'mrp_expired'
        assert participant.posted_in_round_when_removed is False
        assert participant.skip_invite_credits_on_return is True  # Rule 3
        assert participant.observer_since is not None

    def test_move_to_observer_mrp_expired_with_post(self):
        """Test moving user to observer due to MRP expiration after posting."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        ObserverService.move_to_observer(
            participant,
            reason='mrp_expired',
            posted_in_round=True
        )

        participant.refresh_from_db()
        assert participant.role == 'temporary_observer'
        assert participant.observer_reason == 'mrp_expired'
        assert participant.posted_in_round_when_removed is True
        # Credits should be skipped only when didn't post (rule 3)
        assert participant.skip_invite_credits_on_return is False

    def test_move_to_observer_mutual_removal_no_post(self):
        """Test kamikaze without posting - skip credits."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )

        participant.refresh_from_db()
        assert participant.role == 'temporary_observer'
        assert participant.observer_reason == 'mutual_removal'
        assert participant.posted_in_round_when_removed is False
        assert participant.skip_invite_credits_on_return is True  # Rule 4
        assert participant.removal_count == 1

    def test_move_to_observer_mutual_removal_with_post(self):
        """Test kamikaze after posting - still skip credits."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=True
        )

        participant.refresh_from_db()
        assert participant.role == 'temporary_observer'
        assert participant.observer_reason == 'mutual_removal'
        assert participant.posted_in_round_when_removed is True
        assert participant.skip_invite_credits_on_return is True  # Rule 4: ALWAYS skip
        assert participant.removal_count == 1

    def test_move_to_observer_increments_removal_count(self):
        """Test removal count increments for mutual removal."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        initial_count = participant.removal_count

        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )

        participant.refresh_from_db()
        assert participant.removal_count == initial_count + 1

    def test_move_to_observer_non_mutual_removal_no_count(self):
        """Test removal count not incremented for non-kamikaze."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        initial_count = participant.removal_count

        ObserverService.move_to_observer(
            participant,
            reason='mrp_expired',
            posted_in_round=False
        )

        participant.refresh_from_db()
        assert participant.removal_count == initial_count

    # Test can_rejoin
    def test_can_rejoin_active_participant(self):
        """Test active participant can always rejoin."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_initiator(self):
        """Test initiator can always rejoin."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[0]
        )

        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_permanent_observer(self):
        """Test permanent observer can never rejoin."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        participant.role = 'permanent_observer'
        participant.save()

        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is False
        assert reason == "permanent"

    def test_can_rejoin_mutual_removal_before_posting_same_round_too_soon(self):
        """Test kamikaze before posting - cannot rejoin before 1 MRP elapsed."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer just now
        participant.role = 'temporary_observer'
        participant.observer_since = timezone.now()
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is False
        assert 'wait_' in reason
        assert '_minutes' in reason

    def test_can_rejoin_mutual_removal_before_posting_same_round_after_mrp(self):
        """Test kamikaze before posting - can rejoin after 1 MRP elapsed."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer 35 minutes ago (MRP is 30 minutes)
        participant.role = 'temporary_observer'
        participant.observer_since = timezone.now() - timedelta(minutes=35)
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_mutual_removal_before_posting_later_round(self):
        """Test kamikaze before posting - can rejoin in later round."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        # Create round 2
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_mutual_removal_after_posting_must_skip_next_round(self):
        """Test kamikaze after posting - must skip entire next round."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1 after posting
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = True
        participant.save()

        # Create round 2 (next round)
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        # Cannot rejoin in round 2 (must skip)
        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)

        assert can_rejoin is False
        assert 'must_skip_round_2' in reason
        assert 'rejoin_in_round_3' in reason

    def test_can_rejoin_mutual_removal_after_posting_can_rejoin_round_n_plus_2(self):
        """Test kamikaze after posting - can rejoin in round N+2."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1 after posting
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = True
        participant.save()

        # Create round 3 (N+2)
        round3 = Round.objects.create(
            discussion=self.discussion,
            round_number=3,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        # Can rejoin in round 3
        can_rejoin, reason = ObserverService.can_rejoin(participant, round3)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_mrp_expired_cannot_rejoin_same_round(self):
        """Test MRP expired - cannot rejoin in same round."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1 due to MRP
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mrp_expired'
        participant.save()

        # Cannot rejoin in same round
        can_rejoin, reason = ObserverService.can_rejoin(participant, self.round1)

        assert can_rejoin is False
        assert reason == 'must_wait_for_next_round'

    def test_can_rejoin_mrp_expired_next_round_too_soon(self):
        """Test MRP expired - cannot rejoin until 1 MRP in next round."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mrp_expired'
        participant.save()

        # Create round 2 that just started
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now() - timedelta(minutes=5),  # Started 5 min ago
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        # Cannot rejoin yet (need 30 minutes)
        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)

        assert can_rejoin is False
        assert 'wait_' in reason
        assert '_minutes_in_round_2' in reason

    def test_can_rejoin_mrp_expired_next_round_after_mrp(self):
        """Test MRP expired - can rejoin after 1 MRP in next round."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mrp_expired'
        participant.save()

        # Create round 2 that started 35 minutes ago
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now() - timedelta(minutes=35),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        # Can rejoin now
        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)

        assert can_rejoin is True
        assert reason == ""

    def test_can_rejoin_mrp_expired_later_round(self):
        """Test MRP expired - can rejoin in rounds after next."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer in round 1
        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mrp_expired'
        participant.save()

        # Create round 3
        round3 = Round.objects.create(
            discussion=self.discussion,
            round_number=3,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        # Can rejoin in round 3
        can_rejoin, reason = ObserverService.can_rejoin(participant, round3)

        assert can_rejoin is True
        assert reason == ""

    # Test get_wait_period_end
    def test_get_wait_period_end_mutual_removal_before_posting(self):
        """Test wait period calculation for kamikaze before posting."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        observer_time = timezone.now() - timedelta(minutes=10)
        participant.role = 'temporary_observer'
        participant.observer_since = observer_time
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        wait_end = ObserverService.get_wait_period_end(participant, self.round1)

        assert wait_end is not None
        expected_end = observer_time + timedelta(minutes=self.round1.final_mrp_minutes)
        # Allow 1 second tolerance for test timing
        assert abs((wait_end - expected_end).total_seconds()) < 1

    def test_get_wait_period_end_mutual_removal_after_posting(self):
        """Test wait period for kamikaze after posting - next round + 1 MRP."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = True
        participant.save()

        # Create next round
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        wait_end = ObserverService.get_wait_period_end(participant, self.round1)

        assert wait_end is not None
        expected_end = round2.start_time + timedelta(minutes=round2.final_mrp_minutes)
        # Allow 1 second tolerance
        assert abs((wait_end - expected_end).total_seconds()) < 1

    def test_get_wait_period_end_mrp_expired(self):
        """Test wait period for MRP expired - next round + 1 MRP."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        participant.role = 'temporary_observer'
        participant.observer_since = self.round1.start_time
        participant.observer_reason = 'mrp_expired'
        participant.save()

        # Create next round
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        wait_end = ObserverService.get_wait_period_end(participant, self.round1)

        assert wait_end is not None
        expected_end = round2.start_time + timedelta(minutes=round2.final_mrp_minutes)
        # Allow 1 second tolerance
        assert abs((wait_end - expected_end).total_seconds()) < 1

    def test_get_wait_period_end_not_observer(self):
        """Test wait period returns None for non-observer."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        wait_end = ObserverService.get_wait_period_end(participant, self.round1)

        assert wait_end is None

    # Test rejoin_as_active
    def test_rejoin_as_active_success(self):
        """Test successfully rejoining as active participant."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer 35 minutes ago
        participant.role = 'temporary_observer'
        participant.observer_since = timezone.now() - timedelta(minutes=35)
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        # Should be able to rejoin
        ObserverService.rejoin_as_active(participant)

        participant.refresh_from_db()
        assert participant.role == 'active'
        assert participant.observer_since is None
        assert participant.observer_reason is None
        assert participant.posted_in_round_when_removed is False

    def test_rejoin_as_active_too_soon_raises_error(self):
        """Test rejoining too soon raises error."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer just now
        participant.role = 'temporary_observer'
        participant.observer_since = timezone.now()
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        # Should not be able to rejoin
        with pytest.raises(ValueError) as exc_info:
            ObserverService.rejoin_as_active(participant)

        assert 'Cannot rejoin' in str(exc_info.value)

    def test_rejoin_as_active_no_active_round_raises_error(self):
        """Test rejoining with no active round raises error."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        # Move to observer
        participant.role = 'temporary_observer'
        participant.observer_since = timezone.now() - timedelta(minutes=60)
        participant.observer_reason = 'mutual_removal'
        participant.posted_in_round_when_removed = False
        participant.save()

        # Mark round as not in progress
        self.round1.status = 'completed'
        self.round1.save()

        # Should raise error
        with pytest.raises(ValueError) as exc_info:
            ObserverService.rejoin_as_active(participant)

        assert 'No active round' in str(exc_info.value)

    # Test make_permanent_observer
    def test_make_permanent_observer(self):
        """Test making user permanent observer."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        initial_platform_acquired = self.users[1].platform_invites_acquired
        initial_platform_banked = self.users[1].platform_invites_banked

        assert initial_platform_acquired > 0
        assert initial_platform_banked > 0

        ObserverService.make_permanent_observer(participant, 'severe_violation')

        participant.refresh_from_db()
        self.users[1].refresh_from_db()

        assert participant.role == 'permanent_observer'
        assert participant.observer_reason == 'severe_violation'
        assert participant.observer_since is not None
        assert self.users[1].platform_invites_acquired == 0
        assert self.users[1].platform_invites_banked == 0

    def test_make_permanent_observer_resets_invites_only(self):
        """Test permanent observer resets platform invites but not discussion invites."""
        participant = DiscussionParticipant.objects.get(
            discussion=self.discussion,
            user=self.users[1]
        )

        initial_discussion_acquired = self.users[1].discussion_invites_acquired
        initial_discussion_banked = self.users[1].discussion_invites_banked

        ObserverService.make_permanent_observer(participant, 'severe_violation')

        self.users[1].refresh_from_db()

        # Discussion invites should not be affected
        assert self.users[1].discussion_invites_acquired == initial_discussion_acquired
        assert self.users[1].discussion_invites_banked == initial_discussion_banked
