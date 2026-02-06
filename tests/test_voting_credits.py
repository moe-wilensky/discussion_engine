"""
Tests for voting credits system.

Verifies that users earn 0.2 platform invites + 1 discussion invite
when participating in any voting activity during a round's voting phase.
"""

from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from core.models import User, Discussion, Round, DiscussionParticipant, PlatformConfig
from core.services.invite_service import InviteService
from core.services.voting_service import VotingService
from core.services.moderation_voting_service import ModerationVotingService
from tests.factories import UserFactory, DiscussionFactory, RoundFactory


class VotingCreditsTestCase(TestCase):
    """Test voting credits awarding system"""

    def setUp(self):
        """Create test fixtures"""
        self.config = PlatformConfig.load()

        # Create discussion with initiator
        self.discussion = DiscussionFactory()
        self.initiator = self.discussion.initiator

        # Create round in voting phase
        self.round = RoundFactory(
            discussion=self.discussion,
            round_number=1,
            status="voting",
            final_mrp_minutes=30.0
        )

        # Create two voters who responded in the round
        self.voter1 = UserFactory()
        self.voter2 = UserFactory()

        # Make them participants
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=self.voter1,
            role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=self.voter2,
            role="active"
        )

        # Create responses so they're eligible voters
        from core.models import Response
        Response.objects.create(
            round=self.round,
            user=self.voter1,
            content="Test response from voter1"
        )
        Response.objects.create(
            round=self.round,
            user=self.voter2,
            content="Test response from voter2"
        )

    def test_earn_invite_from_vote_amounts(self):
        """Test that earn_invite_from_vote awards correct amounts"""
        # Record starting balances
        initial_platform = self.voter1.platform_invites_acquired
        initial_discussion = self.voter1.discussion_invites_acquired

        # Award voting credits
        platform_added, discussion_added = InviteService.earn_invite_from_vote(self.voter1)

        # Verify return values
        self.assertEqual(platform_added, Decimal('0.2'))
        self.assertEqual(discussion_added, 1)

        # Refresh and verify user balances
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.2')
        )
        self.assertEqual(
            self.voter1.discussion_invites_acquired,
            initial_discussion + 1
        )

    def test_earn_invite_from_vote_accumulation(self):
        """Test that credits accumulate correctly with multiple calls"""
        initial_platform = self.voter1.platform_invites_acquired
        initial_discussion = self.voter1.discussion_invites_acquired

        # Award credits twice
        InviteService.earn_invite_from_vote(self.voter1)
        InviteService.earn_invite_from_vote(self.voter1)

        # Verify accumulation
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.4')  # 0.2 * 2
        )
        self.assertEqual(
            self.voter1.discussion_invites_acquired,
            initial_discussion + 2  # 1 * 2
        )

    def test_award_voting_credits_first_time(self):
        """Test that credits are awarded on first vote"""
        initial_platform = self.voter1.platform_invites_acquired
        initial_discussion = self.voter1.discussion_invites_acquired

        # Award credits for first time
        result = VotingService._award_voting_credits(self.round, self.voter1)

        # Should return True (credits awarded)
        self.assertTrue(result)

        # Verify credits were awarded
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.2')
        )
        self.assertEqual(
            self.voter1.discussion_invites_acquired,
            initial_discussion + 1
        )

        # Verify tracking
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)

    def test_award_voting_credits_deduplication(self):
        """Test that credits are NOT awarded on second vote in same round"""
        # Award credits first time
        result1 = VotingService._award_voting_credits(self.round, self.voter1)
        self.assertTrue(result1)

        # Record balances after first award
        self.voter1.refresh_from_db()
        platform_after_first = self.voter1.platform_invites_acquired
        discussion_after_first = self.voter1.discussion_invites_acquired

        # Try to award again in same round
        result2 = VotingService._award_voting_credits(self.round, self.voter1)
        self.assertFalse(result2)  # Should return False

        # Verify no additional credits awarded
        self.voter1.refresh_from_db()
        self.assertEqual(self.voter1.platform_invites_acquired, platform_after_first)
        self.assertEqual(self.voter1.discussion_invites_acquired, discussion_after_first)

    def test_award_voting_credits_different_rounds(self):
        """Test that credits CAN be awarded in different rounds"""
        # Award credits in round 1
        result1 = VotingService._award_voting_credits(self.round, self.voter1)
        self.assertTrue(result1)

        # Create round 2
        round2 = RoundFactory(
            discussion=self.discussion,
            round_number=2,
            status="voting",
            final_mrp_minutes=30.0
        )

        # Award credits in round 2
        result2 = VotingService._award_voting_credits(round2, self.voter1)
        self.assertTrue(result2)  # Should succeed in different round

        # Verify tracking is separate per round
        self.round.refresh_from_db()
        round2.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)
        self.assertIn(self.voter1.id, round2.voting_credits_awarded)

    def test_mrl_vote_awards_credits(self):
        """Test that MRL voting triggers credit award"""
        initial_platform = self.voter1.platform_invites_acquired

        # Cast parameter vote (includes MRL)
        VotingService.cast_parameter_vote(
            self.voter1,
            self.round,
            mrl_vote="increase",
            rtm_vote="no_change"
        )

        # Verify credits awarded
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.2')
        )

        # Verify tracking
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)

    def test_rtm_vote_awards_credits(self):
        """Test that RTM voting triggers credit award"""
        initial_discussion = self.voter1.discussion_invites_acquired

        # Cast parameter vote (includes RTM)
        VotingService.cast_parameter_vote(
            self.voter1,
            self.round,
            mrl_vote="no_change",
            rtm_vote="decrease"
        )

        # Verify credits awarded
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.discussion_invites_acquired,
            initial_discussion + 1
        )

    def test_removal_vote_awards_credits(self):
        """Test that removal voting triggers credit award"""
        initial_platform = self.voter1.platform_invites_acquired

        # Cast removal vote
        ModerationVotingService.cast_removal_vote(
            self.voter1,
            self.round,
            [self.voter2]
        )

        # Verify credits awarded
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.2')
        )

        # Verify tracking
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)

    def test_multiple_vote_types_one_credit(self):
        """Test that casting MRL + RTM + removal only awards credits once"""
        initial_platform = self.voter1.platform_invites_acquired
        initial_discussion = self.voter1.discussion_invites_acquired

        # Cast parameter vote
        VotingService.cast_parameter_vote(
            self.voter1,
            self.round,
            mrl_vote="increase",
            rtm_vote="decrease"
        )

        # Cast removal vote
        ModerationVotingService.cast_removal_vote(
            self.voter1,
            self.round,
            [self.voter2]
        )

        # Verify only ONE set of credits awarded
        self.voter1.refresh_from_db()
        self.assertEqual(
            self.voter1.platform_invites_acquired,
            initial_platform + Decimal('0.2')  # Not 0.4
        )
        self.assertEqual(
            self.voter1.discussion_invites_acquired,
            initial_discussion + 1  # Not 2
        )

        # Verify voter1 appears only once in tracking
        self.round.refresh_from_db()
        vote_count = self.round.voting_credits_awarded.count(self.voter1.id)
        self.assertEqual(vote_count, 1)

    def test_voting_credits_tracking_persists(self):
        """Test that Round.voting_credits_awarded persists across saves"""
        # Award credits to voter1
        VotingService._award_voting_credits(self.round, self.voter1)

        # Verify tracking
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)

        # Award credits to voter2
        VotingService._award_voting_credits(self.round, self.voter2)

        # Verify both are tracked
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)
        self.assertIn(self.voter2.id, self.round.voting_credits_awarded)
        self.assertEqual(len(self.round.voting_credits_awarded), 2)

        # Save round for unrelated reason
        self.round.status = "completed"
        self.round.save()

        # Verify tracking still intact
        self.round.refresh_from_db()
        self.assertIn(self.voter1.id, self.round.voting_credits_awarded)
        self.assertIn(self.voter2.id, self.round.voting_credits_awarded)
        self.assertEqual(len(self.round.voting_credits_awarded), 2)
