"""
Tests for voting credits mechanic (mechanic #3 in updated system).

This mechanic awards 0.2 platform + 1 discussion invite when a user
participates in any voting activity during a voting phase.

Critical: Credits awarded ONCE per voting session, not per vote.
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from core.models import User, Discussion, Round, DiscussionParticipant
from core.services.invite_service import InviteService
from core.services.voting_service import VotingService
from tests.factories import UserFactory, DiscussionFactory, RoundFactory


@pytest.mark.django_db
class TestVotingCreditsTests:
    """Comprehensive tests for voting credits mechanic."""

    def test_voting_credits_awarded_on_first_vote(self):
        """Verify credits awarded when user votes for first time in round."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)
        round_obj = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        initial_platform = user.platform_invites_acquired
        initial_discussion = user.discussion_invites_acquired

        # Cast a vote (any type - parameter vote)
        VotingService.cast_parameter_vote(user, round_obj, 'increase', 'no_change')

        user.refresh_from_db()
        assert user.platform_invites_acquired == initial_platform + Decimal('0.2')
        assert user.discussion_invites_acquired == initial_discussion + 1

    def test_voting_credits_not_awarded_twice(self):
        """Verify credits NOT awarded on second vote in same round."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)
        round_obj = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        # First vote (parameter vote)
        VotingService.cast_parameter_vote(user, round_obj, 'increase', 'no_change')

        user.refresh_from_db()
        after_first_vote_platform = user.platform_invites_acquired
        after_first_vote_discussion = user.discussion_invites_acquired

        # Second vote in same round (updating vote - this updates the same vote record)
        VotingService.cast_parameter_vote(user, round_obj, 'decrease', 'increase')

        user.refresh_from_db()
        # Credits should be SAME as after first vote
        assert user.platform_invites_acquired == after_first_vote_platform
        assert user.discussion_invites_acquired == after_first_vote_discussion

    def test_voting_credits_awarded_in_different_rounds(self):
        """Verify credits CAN be awarded again in a new round."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)
        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        # Vote in round 1
        VotingService.cast_parameter_vote(user, round1, 'increase', 'no_change')

        user.refresh_from_db()
        after_round1_platform = user.platform_invites_acquired
        after_round1_discussion = user.discussion_invites_acquired

        # Create round 2
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status='voting'
        )

        # Vote in round 2
        VotingService.cast_parameter_vote(user, round2, 'decrease', 'increase')

        user.refresh_from_db()
        # Should have earned credits AGAIN
        assert user.platform_invites_acquired == after_round1_platform + Decimal('0.2')
        assert user.discussion_invites_acquired == after_round1_discussion + 1

    def test_voting_credits_tracking_persists(self):
        """Verify tracking field persists across round saves."""
        user = UserFactory()
        discussion = DiscussionFactory(initiator=user)
        round_obj = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        VotingService.cast_parameter_vote(user, round_obj, 'increase', 'no_change')

        round_obj.refresh_from_db()
        assert user.id in round_obj.voting_credits_awarded

        # Save round again (simulating other updates)
        round_obj.save()

        round_obj.refresh_from_db()
        # Tracking should still persist
        assert user.id in round_obj.voting_credits_awarded

    def test_multiple_users_can_earn_credits(self):
        """Verify multiple users can all earn credits in same round."""
        from core.models import Response

        user1 = UserFactory()
        user2 = UserFactory()
        discussion = DiscussionFactory(initiator=user1)

        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user2,
            role='active'
        )

        round_obj = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='in_progress'  # Start in_progress so users can post
        )

        # Both users post responses (needed for eligibility to vote)
        Response.objects.create(
            user=user1,
            round=round_obj,
            content='Response from user1',
            character_count=20
        )
        Response.objects.create(
            user=user2,
            round=round_obj,
            content='Response from user2',
            character_count=20
        )

        # Change to voting status
        round_obj.status = 'voting'
        round_obj.save()

        # Both users vote
        VotingService.cast_parameter_vote(user1, round_obj, 'increase', 'no_change')
        VotingService.cast_parameter_vote(user2, round_obj, 'decrease', 'increase')

        round_obj.refresh_from_db()
        # Both should be tracked
        assert user1.id in round_obj.voting_credits_awarded
        assert user2.id in round_obj.voting_credits_awarded
