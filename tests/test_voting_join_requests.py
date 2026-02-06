"""
Tests for join request voting system.

Tests voting-based join request approval/denial during inter-round voting.
"""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import (
    Discussion,
    Round,
    JoinRequest,
    JoinRequestVote,
    DiscussionParticipant,
    PlatformConfig,
    User,
)
from core.services.voting_service import VotingService
from core.services.multi_round_service import MultiRoundService
from core.services.join_request import JoinRequestService
from tests.factories import (
    UserFactory,
    DiscussionFactory,
    RoundFactory,
    ResponseFactory,
    JoinRequestFactory,
)


@pytest.mark.django_db
class TestRecordJoinRequestVote:
    """Test recording join request votes"""

    def test_record_join_request_vote_approve(self):
        """Test can record approval vote"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create voter
        voter = UserFactory()

        # Record approval vote
        vote = VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter,
            join_request=join_request,
            approve=True
        )

        # Verify vote created
        assert vote is not None
        assert vote.approve is True
        assert vote.voter == voter
        assert vote.join_request == join_request
        assert vote.round == round_obj

    def test_record_join_request_vote_deny(self):
        """Test can record denial vote"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create voter
        voter = UserFactory()

        # Record denial vote
        vote = VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter,
            join_request=join_request,
            approve=False
        )

        # Verify vote created
        assert vote is not None
        assert vote.approve is False
        assert vote.voter == voter
        assert vote.join_request == join_request

    def test_record_join_request_vote_duplicate(self):
        """Test prevents duplicate votes"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create voter
        voter = UserFactory()

        # Record first vote
        VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter,
            join_request=join_request,
            approve=True
        )

        # Try to vote again
        with pytest.raises(ValidationError) as exc_info:
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=False
            )

        assert "already voted" in str(exc_info.value).lower()

    def test_record_join_request_vote_awards_credits(self):
        """Test voting triggers credits award"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create voter with known credit amounts
        voter = UserFactory()
        initial_platform = voter.platform_invites_acquired
        initial_discussion = voter.discussion_invites_acquired

        # Record vote
        VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter,
            join_request=join_request,
            approve=True
        )

        # Refresh voter
        voter.refresh_from_db()

        # Verify credits awarded
        assert voter.platform_invites_acquired > initial_platform
        assert voter.discussion_invites_acquired > initial_discussion

        # Verify only awarded once even if voting again on different request
        join_request2 = JoinRequestFactory(
            discussion=discussion,
            requester=UserFactory(),
            status='pending'
        )

        VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter,
            join_request=join_request2,
            approve=True
        )

        voter.refresh_from_db()
        # Credits should not increase again
        from decimal import Decimal
        assert voter.platform_invites_acquired == Decimal(str(initial_platform + 0.2))
        assert voter.discussion_invites_acquired == Decimal(str(initial_discussion + 1))


@pytest.mark.django_db
class TestGetJoinRequestVoteCounts:
    """Test getting vote counts for join requests"""

    def test_get_join_request_vote_counts(self):
        """Test counts are accurate"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create 3 approve votes
        for _ in range(3):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=True
            )

        # Create 2 deny votes
        for _ in range(2):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=False
            )

        # Get counts
        counts = VotingService.get_join_request_vote_counts(round_obj, join_request)

        # Verify counts
        assert counts['approve'] == 3
        assert counts['deny'] == 2
        assert counts['total'] == 5


@pytest.mark.django_db
class TestProcessJoinRequestVotes:
    """Test processing join request votes"""

    def test_process_join_request_votes_majority_approve(self):
        """Test >50% approves request"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create 3 approve votes (60%)
        for _ in range(3):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=True
            )

        # Create 2 deny votes (40%)
        for _ in range(2):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=False
            )

        # Process votes
        results = VotingService.process_join_request_votes(round_obj)

        # Verify request approved
        assert len(results['approved']) == 1
        assert results['approved'][0] == join_request
        assert len(results['denied']) == 0
        assert len(results['pending']) == 0

        # Verify status updated
        join_request.refresh_from_db()
        assert join_request.status == 'approved'

        # Verify participant created
        assert DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester,
            role='active'
        ).exists()

    def test_process_join_request_votes_majority_deny(self):
        """Test <50% denies request"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create 2 approve votes (40%)
        for _ in range(2):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=True
            )

        # Create 3 deny votes (60%)
        for _ in range(3):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=False
            )

        # Process votes
        results = VotingService.process_join_request_votes(round_obj)

        # Verify request denied
        assert len(results['approved']) == 0
        assert len(results['denied']) == 1
        assert results['denied'][0] == join_request
        assert len(results['pending']) == 0

        # Verify status updated
        join_request.refresh_from_db()
        assert join_request.status == 'declined'

        # Verify participant NOT created
        assert not DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester,
            role='active'
        ).exists()

    def test_process_join_request_votes_tie_stays_pending(self):
        """Test 50% tie stays pending"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Create 2 approve votes (50%)
        for _ in range(2):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=True
            )

        # Create 2 deny votes (50%)
        for _ in range(2):
            voter = UserFactory()
            VotingService.record_join_request_vote(
                round_obj=round_obj,
                voter=voter,
                join_request=join_request,
                approve=False
            )

        # Process votes
        results = VotingService.process_join_request_votes(round_obj)

        # Verify request stays pending
        assert len(results['approved']) == 0
        assert len(results['denied']) == 0
        assert len(results['pending']) == 1
        assert results['pending'][0] == join_request

        # Verify status still pending
        join_request.refresh_from_db()
        assert join_request.status == 'pending'

    def test_process_join_request_votes_no_votes_stays_pending(self):
        """Test no votes = pending"""
        # Create discussion with round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create join request with NO votes
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Process votes
        results = VotingService.process_join_request_votes(round_obj)

        # Verify request stays pending
        assert len(results['approved']) == 0
        assert len(results['denied']) == 0
        assert len(results['pending']) == 1
        assert results['pending'][0] == join_request

        # Verify status still pending
        join_request.refresh_from_db()
        assert join_request.status == 'pending'


@pytest.mark.django_db
class TestCloseVotingAndCreateNextRound:
    """Test full round transition with join request voting"""

    def test_close_voting_and_create_next_round(self):
        """Test full round transition processes all votes"""
        # Create discussion with active participants
        discussion = DiscussionFactory()
        round_obj = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        # Create responses in this round to establish eligible voters
        voter1 = UserFactory()
        voter2 = UserFactory()
        ResponseFactory(round=round_obj, user=voter1)
        ResponseFactory(round=round_obj, user=voter2)

        # Ensure voters are participants
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter1,
            role='active'
        )
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter2,
            role='active'
        )

        # Create join request with majority approval
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Both voters approve (100%)
        VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter1,
            join_request=join_request,
            approve=True
        )
        VotingService.record_join_request_vote(
            round_obj=round_obj,
            voter=voter2,
            join_request=join_request,
            approve=True
        )

        # Close voting and create next round
        next_round = MultiRoundService.close_voting_and_create_next_round(round_obj)

        # Verify next round created
        assert next_round is not None
        assert next_round.round_number == 2
        assert next_round.discussion == discussion
        assert next_round.status == 'in_progress'

        # Verify join request was processed and approved
        join_request.refresh_from_db()
        assert join_request.status == 'approved'

        # Verify requester is now participant
        assert DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester,
            role='active'
        ).exists()
