"""
Comprehensive integration tests for VotingService.

Focus: Achieve 85%+ coverage of voting_service.py
Current: 31.93% → Target: 85%+
"""
from decimal import Decimal
import pytest
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import (
    Discussion, Round, User, DiscussionParticipant, JoinRequest,
    PlatformConfig, Vote, JoinRequestVote
)
from core.services.voting_service import VotingService
from tests.factories import UserFactory, DiscussionFactory


class VotingServiceIntegrationTests(TransactionTestCase):
    """
    Integration tests for VotingService.

    Uses TransactionTestCase for transaction testing and to avoid
    database constraint issues with Round.voting_credits_awarded.
    """

    def setUp(self):
        """Set up test data with proper constraints."""
        # Get or create platform config (singleton pattern)
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

        # Use factory to create users with proper fields
        self.users = []
        for i in range(5):
            user = UserFactory.create(
                username=f'user{i}',
                email=f'user{i}@test.com',
                platform_invites_acquired=Decimal('5.0'),
                platform_invites_banked=Decimal('5.0'),
                discussion_invites_acquired=25,
                discussion_invites_banked=25
            )
            user.set_password('testpass123')
            user.save()
            self.users.append(user)

        # Use factory to create discussion (auto-creates initiator participant)
        self.discussion = DiscussionFactory.create(
            topic_headline='Test Discussion',
            topic_details='Test discussion for voting service tests',
            initiator=self.users[0],
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=5
        )

        # Create participants (users[0] already created by factory as initiator)
        for user in self.users[1:4]:  # Skip users[0] since factory created them
            DiscussionParticipant.objects.create(
                discussion=self.discussion,
                user=user,
                role='active'
            )

        # Create round with explicit voting_credits_awarded
        self.round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            status='voting',
            voting_credits_awarded=[]  # Explicit to avoid DB constraint issues
        )

    # Test _award_voting_credits
    def test_award_voting_credits_first_time(self):
        """Test credits awarded on first vote."""
        initial_platform = self.users[0].platform_invites_banked
        initial_discussion = self.users[0].discussion_invites_banked

        result = VotingService._award_voting_credits(self.round, self.users[0])

        assert result is True
        self.users[0].refresh_from_db()
        assert self.users[0].platform_invites_banked == initial_platform + Decimal('0.2')
        assert self.users[0].discussion_invites_banked == initial_discussion + 1

        # Verify tracking
        self.round.refresh_from_db()
        assert self.users[0].id in self.round.voting_credits_awarded

    def test_award_voting_credits_prevents_duplicate(self):
        """Test credits not awarded twice in same round."""
        # Award once
        VotingService._award_voting_credits(self.round, self.users[0])

        self.users[0].refresh_from_db()
        credits_after_first = self.users[0].platform_invites_banked

        # Try to award again
        result = VotingService._award_voting_credits(self.round, self.users[0])

        assert result is False
        self.users[0].refresh_from_db()
        assert self.users[0].platform_invites_banked == credits_after_first

    def test_award_voting_credits_handles_none_field(self):
        """Test credit awarding when voting_credits_awarded is None."""
        # Set to None (edge case)
        self.round.voting_credits_awarded = None
        self.round.save()

        result = VotingService._award_voting_credits(self.round, self.users[0])

        assert result is True
        self.round.refresh_from_db()
        assert self.users[0].id in self.round.voting_credits_awarded

    # Test get_eligible_voters
    def test_get_eligible_voters_includes_responders(self):
        """Test eligible voters include users who responded."""
        from core.models import Response

        # Create responses
        Response.objects.create(
            round=self.round,
            user=self.users[0],
            content='A' * 100,
            is_draft=False
        )
        Response.objects.create(
            round=self.round,
            user=self.users[1],
            content='B' * 100,
            is_draft=False
        )

        eligible = VotingService.get_eligible_voters(self.round)

        assert self.users[0] in eligible
        assert self.users[1] in eligible

    def test_get_eligible_voters_includes_initiator(self):
        """Test eligible voters always include discussion initiator."""
        # No responses yet
        eligible = VotingService.get_eligible_voters(self.round)

        # Initiator should still be eligible
        assert self.users[0] in eligible

    def test_get_eligible_voters_excludes_non_responders(self):
        """Test users who didn't respond are not eligible (except initiator)."""
        from core.models import Response

        # Only user 0 responds
        Response.objects.create(
            round=self.round,
            user=self.users[0],
            content='A' * 100,
            is_draft=False
        )

        eligible = VotingService.get_eligible_voters(self.round)

        # User 2 didn't respond and isn't initiator
        assert self.users[2] not in eligible

    # Test cast_parameter_vote
    def test_cast_parameter_vote_creates_vote(self):
        """Test casting parameter vote creates Vote record."""
        from core.models import Response

        # Make user eligible
        Response.objects.create(
            round=self.round,
            user=self.users[1],
            content='A' * 100,
            is_draft=False
        )

        vote = VotingService.cast_parameter_vote(
            self.users[1],
            self.round,
            'increase',
            'decrease'
        )

        assert vote is not None
        assert vote.mrl_vote == 'increase'
        assert vote.rtm_vote == 'decrease'
        assert vote.user == self.users[1]

    def test_cast_parameter_vote_awards_credits(self):
        """Test casting vote awards credits."""
        from core.models import Response

        Response.objects.create(
            round=self.round,
            user=self.users[1],
            content='A' * 100,
            is_draft=False
        )

        initial_platform = self.users[1].platform_invites_banked

        VotingService.cast_parameter_vote(
            self.users[1],
            self.round,
            'increase',
            'no_change'
        )

        self.users[1].refresh_from_db()
        assert self.users[1].platform_invites_banked == initial_platform + Decimal('0.2')

    def test_cast_parameter_vote_rejects_ineligible_user(self):
        """Test non-eligible user cannot vote."""
        with pytest.raises(ValueError, match="not eligible"):
            VotingService.cast_parameter_vote(
                self.users[2],  # Didn't respond, not initiator
                self.round,
                'increase',
                'no_change'
            )

    def test_cast_parameter_vote_rejects_invalid_choice(self):
        """Test invalid vote choice raises error."""
        from core.models import Response

        Response.objects.create(
            round=self.round,
            user=self.users[1],
            content='A' * 100,
            is_draft=False
        )

        with pytest.raises(ValueError, match="Invalid vote choice"):
            VotingService.cast_parameter_vote(
                self.users[1],
                self.round,
                'invalid',  # Invalid choice
                'no_change'
            )

    def test_cast_parameter_vote_updates_existing(self):
        """Test casting vote again updates existing vote."""
        from core.models import Response

        Response.objects.create(
            round=self.round,
            user=self.users[1],
            content='A' * 100,
            is_draft=False
        )

        # First vote
        vote1 = VotingService.cast_parameter_vote(
            self.users[1],
            self.round,
            'increase',
            'no_change'
        )

        # Second vote (update)
        vote2 = VotingService.cast_parameter_vote(
            self.users[1],
            self.round,
            'decrease',  # Changed
            'increase'   # Changed
        )

        # Should be same vote object, updated
        assert vote1.id == vote2.id
        assert vote2.mrl_vote == 'decrease'
        assert vote2.rtm_vote == 'increase'

    # Test count_votes
    def test_count_votes_accurate_counts(self):
        """Test vote counting returns accurate counts."""
        from core.models import Response

        # Create responses and votes
        for i in range(3):
            Response.objects.create(
                round=self.round,
                user=self.users[i],
                content='A' * 100,
                is_draft=False
            )

        Vote.objects.create(round=self.round, user=self.users[0], mrl_vote='increase', rtm_vote='no_change')
        Vote.objects.create(round=self.round, user=self.users[1], mrl_vote='increase', rtm_vote='decrease')
        Vote.objects.create(round=self.round, user=self.users[2], mrl_vote='no_change', rtm_vote='decrease')

        counts = VotingService.count_votes(self.round, 'mrl')

        assert counts['increase'] == 2
        assert counts['no_change'] == 1
        assert counts['decrease'] == 0
        assert counts['total_eligible'] == 3  # 3 responders (initiator is users[0])

    def test_count_votes_includes_not_voted(self):
        """Test count_votes tracks users who didn't vote."""
        from core.models import Response

        # 3 eligible, but only 1 votes
        for i in range(3):
            Response.objects.create(
                round=self.round,
                user=self.users[i],
                content='A' * 100,
                is_draft=False
            )

        Vote.objects.create(round=self.round, user=self.users[0], mrl_vote='increase', rtm_vote='no_change')

        counts = VotingService.count_votes(self.round, 'mrl')

        assert counts['not_voted'] == 2
        assert counts['total_eligible'] == 3

    def test_count_votes_rejects_invalid_parameter(self):
        """Test count_votes raises error for invalid parameter."""
        with pytest.raises(ValueError, match="Invalid parameter"):
            VotingService.count_votes(self.round, 'invalid')

    # Test resolve_vote
    def test_resolve_vote_increase_wins(self):
        """Test increase wins with majority."""
        from core.models import Response

        for i in range(3):
            Response.objects.create(
                round=self.round,
                user=self.users[i],
                content='A' * 100,
                is_draft=False
            )

        # 2 increase, 1 no_change
        Vote.objects.create(round=self.round, user=self.users[0], mrl_vote='increase', rtm_vote='no_change')
        Vote.objects.create(round=self.round, user=self.users[1], mrl_vote='increase', rtm_vote='no_change')
        Vote.objects.create(round=self.round, user=self.users[2], mrl_vote='no_change', rtm_vote='no_change')

        result = VotingService.resolve_vote(self.round, 'mrl')

        assert result == 'increase'

    def test_resolve_vote_abstentions_count_as_no_change(self):
        """Test abstentions (not voting) count toward no_change."""
        from core.models import Response

        # 4 eligible, but only 1 votes for increase
        for i in range(4):
            Response.objects.create(
                round=self.round,
                user=self.users[i],
                content='A' * 100,
                is_draft=False
            )

        Vote.objects.create(round=self.round, user=self.users[0], mrl_vote='increase', rtm_vote='no_change')
        # Users 1, 2, 3 don't vote (3 abstentions)

        result = VotingService.resolve_vote(self.round, 'mrl')

        # 3 abstentions + 0 explicit no_change = 3 total no_change vs 1 increase
        assert result == 'no_change'

    def test_resolve_vote_tie_goes_to_no_change(self):
        """Test tie votes default to no_change."""
        from core.models import Response

        for i in range(2):
            Response.objects.create(
                round=self.round,
                user=self.users[i],
                content='A' * 100,
                is_draft=False
            )

        # 1 increase, 1 decrease (tie)
        Vote.objects.create(round=self.round, user=self.users[0], mrl_vote='increase', rtm_vote='no_change')
        Vote.objects.create(round=self.round, user=self.users[1], mrl_vote='decrease', rtm_vote='no_change')

        result = VotingService.resolve_vote(self.round, 'mrl')

        assert result == 'no_change'

    # Test apply_parameter_change
    def test_apply_parameter_change_mrl_increase(self):
        """Test MRL increases by correct percentage."""
        initial_mrl = self.discussion.max_response_length_chars
        expected_mrl = int(initial_mrl * 1.2)  # 20% increase

        VotingService.apply_parameter_change(
            self.discussion,
            'mrl',
            'increase',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.max_response_length_chars == expected_mrl

    def test_apply_parameter_change_mrl_decrease(self):
        """Test MRL decreases by correct percentage."""
        initial_mrl = self.discussion.max_response_length_chars
        expected_mrl = int(initial_mrl * 0.8)  # 20% decrease

        VotingService.apply_parameter_change(
            self.discussion,
            'mrl',
            'decrease',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.max_response_length_chars == expected_mrl

    def test_apply_parameter_change_mrl_clamped_to_min(self):
        """Test MRL cannot go below minimum."""
        self.discussion.max_response_length_chars = 110
        self.discussion.save()

        # Try to decrease (would be 88, but min is 100)
        VotingService.apply_parameter_change(
            self.discussion,
            'mrl',
            'decrease',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.max_response_length_chars == 100  # Clamped to min

    def test_apply_parameter_change_mrl_clamped_to_max(self):
        """Test MRL cannot exceed maximum."""
        self.discussion.max_response_length_chars = 4900
        self.discussion.save()

        # Try to increase (would be 5880, but max is 5000)
        VotingService.apply_parameter_change(
            self.discussion,
            'mrl',
            'increase',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.max_response_length_chars == 5000  # Clamped to max

    def test_apply_parameter_change_rtm_increase(self):
        """Test RTM increases correctly."""
        initial_rtm = self.discussion.response_time_multiplier
        expected_rtm = initial_rtm * 1.2  # 20% increase

        VotingService.apply_parameter_change(
            self.discussion,
            'rtm',
            'increase',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.response_time_multiplier == pytest.approx(expected_rtm)

    def test_apply_parameter_change_no_change(self):
        """Test no_change doesn't modify value."""
        initial_mrl = self.discussion.max_response_length_chars

        VotingService.apply_parameter_change(
            self.discussion,
            'mrl',
            'no_change',
            self.config
        )

        self.discussion.refresh_from_db()
        assert self.discussion.max_response_length_chars == initial_mrl

    # Test record_join_request_vote
    def test_record_join_request_vote_approve(self):
        """Test recording approval vote on join request."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        vote = VotingService.record_join_request_vote(
            self.round,
            self.users[0],
            join_request,
            approve=True
        )

        assert vote.approve is True
        assert vote.join_request == join_request
        assert vote.voter == self.users[0]

    def test_record_join_request_vote_deny(self):
        """Test recording denial vote on join request."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        vote = VotingService.record_join_request_vote(
            self.round,
            self.users[0],
            join_request,
            approve=False
        )

        assert vote.approve is False

    def test_record_join_request_vote_prevents_duplicate(self):
        """Test user cannot vote twice on same request."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # First vote
        VotingService.record_join_request_vote(
            self.round,
            self.users[0],
            join_request,
            True
        )

        # Second vote should raise ValidationError
        with pytest.raises(ValidationError, match="already voted"):
            VotingService.record_join_request_vote(
                self.round,
                self.users[0],
                join_request,
                False
            )

    def test_record_join_request_vote_awards_credits(self):
        """Test voting on join request awards credits."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        initial_platform = self.users[0].platform_invites_banked

        VotingService.record_join_request_vote(
            self.round,
            self.users[0],
            join_request,
            True
        )

        self.users[0].refresh_from_db()
        assert self.users[0].platform_invites_banked == initial_platform + Decimal('0.2')

    # Test get_join_request_vote_counts
    def test_get_join_request_vote_counts_accurate(self):
        """Test vote count calculation."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # Create votes (3 approve, 1 deny)
        for i in range(3):
            JoinRequestVote.objects.create(
                round=self.round,
                voter=self.users[i],
                join_request=join_request,
                approve=True
            )

        JoinRequestVote.objects.create(
            round=self.round,
            voter=self.users[3],
            join_request=join_request,
            approve=False
        )

        counts = VotingService.get_join_request_vote_counts(
            self.round,
            join_request
        )

        assert counts['approve'] == 3
        assert counts['deny'] == 1
        assert counts['total'] == 4

    def test_get_join_request_vote_counts_no_votes(self):
        """Test vote counts when no votes cast."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        counts = VotingService.get_join_request_vote_counts(
            self.round,
            join_request
        )

        assert counts['approve'] == 0
        assert counts['deny'] == 0
        assert counts['total'] == 0

    # Test process_join_request_votes
    def test_process_join_request_votes_majority_approve(self):
        """Test >50% approval approves request."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # 3 approve, 1 deny = 75% approval
        for i in range(3):
            JoinRequestVote.objects.create(
                round=self.round,
                voter=self.users[i],
                join_request=join_request,
                approve=True
            )

        JoinRequestVote.objects.create(
            round=self.round,
            voter=self.users[3],
            join_request=join_request,
            approve=False
        )

        results = VotingService.process_join_request_votes(self.round)

        assert join_request in results['approved']
        join_request.refresh_from_db()
        assert join_request.status == 'approved'

    def test_process_join_request_votes_majority_deny(self):
        """Test <50% approval denies request."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # 1 approve, 3 deny = 25% approval
        JoinRequestVote.objects.create(
            round=self.round,
            voter=self.users[0],
            join_request=join_request,
            approve=True
        )

        for i in range(1, 4):
            JoinRequestVote.objects.create(
                round=self.round,
                voter=self.users[i],
                join_request=join_request,
                approve=False
            )

        results = VotingService.process_join_request_votes(self.round)

        assert join_request in results['denied']
        join_request.refresh_from_db()
        assert join_request.status == 'declined'

    def test_process_join_request_votes_tie_stays_pending(self):
        """Test 50/50 tie keeps request pending."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # 2 approve, 2 deny = 50% exactly
        for i in range(2):
            JoinRequestVote.objects.create(
                round=self.round,
                voter=self.users[i],
                join_request=join_request,
                approve=True
            )

        for i in range(2, 4):
            JoinRequestVote.objects.create(
                round=self.round,
                voter=self.users[i],
                join_request=join_request,
                approve=False
            )

        results = VotingService.process_join_request_votes(self.round)

        assert join_request in results['pending']
        join_request.refresh_from_db()
        assert join_request.status == 'pending'

    def test_process_join_request_votes_no_votes_stays_pending(self):
        """Test request without votes stays pending."""
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # No votes cast
        results = VotingService.process_join_request_votes(self.round)

        assert join_request in results['pending']
        join_request.refresh_from_db()
        assert join_request.status == 'pending'
