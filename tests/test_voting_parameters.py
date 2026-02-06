"""
Tests for parameter voting functionality.

Tests voting eligibility, vote casting, counting, resolution, and parameter changes.
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    Discussion,
    Round,
    Vote,
    DiscussionParticipant,
    PlatformConfig,
    Response,
)
from core.services.voting_service import VotingService


@pytest.mark.django_db
class TestParameterVoting:
    """Test parameter voting (MRL and RTM)"""

    @pytest.fixture
    def setup_voting_scenario(self):
        """Create discussion with completed round ready for voting"""
        config = PlatformConfig.load()

        # Create users
        initiator = User.objects.create_user(
            username="initiator", phone_number="+11234567890", password="test123"
        )
        user1 = User.objects.create_user(
            username="user1", phone_number="+11234567891", password="test123"
        )
        user2 = User.objects.create_user(
            username="user2", phone_number="+11234567892", password="test123"
        )
        user3 = User.objects.create_user(
            username="user3", phone_number="+11234567893", password="test123"
        )

        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Testing voting",
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=initiator,
        )

        # Create participants
        DiscussionParticipant.objects.create(
            discussion=discussion, user=initiator, role="initiator"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user1, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user2, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user3, role="active"
        )

        # Create round
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # Create responses
        Response.objects.create(
            round=round, user=initiator, content="A" * 100, character_count=100
        )
        Response.objects.create(
            round=round, user=user1, content="B" * 100, character_count=100
        )
        Response.objects.create(
            round=round, user=user2, content="C" * 100, character_count=100
        )
        # user3 didn't respond

        return {
            "config": config,
            "initiator": initiator,
            "user1": user1,
            "user2": user2,
            "user3": user3,
            "discussion": discussion,
            "round": round,
        }

    def test_eligible_voters_correct(self, setup_voting_scenario):
        """Eligible voters = initiator + active participants who responded"""
        data = setup_voting_scenario
        round = data["round"]

        eligible = VotingService.get_eligible_voters(round)

        # Should include initiator, user1, user2 (all responded)
        # Should NOT include user3 (didn't respond)
        assert eligible.count() == 3
        assert data["initiator"] in eligible
        assert data["user1"] in eligible
        assert data["user2"] in eligible
        assert data["user3"] not in eligible

    def test_cast_parameter_vote(self, setup_voting_scenario):
        """Cast valid parameter vote"""
        data = setup_voting_scenario
        round = data["round"]

        vote = VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="no_change"
        )

        assert vote.user == data["initiator"]
        assert vote.round == round
        assert vote.mrl_vote == "increase"
        assert vote.rtm_vote == "no_change"

    def test_cast_vote_not_eligible(self, setup_voting_scenario):
        """Cannot vote if not eligible"""
        data = setup_voting_scenario
        round = data["round"]

        with pytest.raises(ValueError, match="not eligible to vote"):
            VotingService.cast_parameter_vote(
                data["user3"],
                round,  # Didn't respond
                mrl_vote="increase",
                rtm_vote="no_change",
            )

    def test_vote_counting_correct(self, setup_voting_scenario):
        """Vote counting is accurate"""
        data = setup_voting_scenario
        round = data["round"]

        # Cast votes
        VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="decrease"
        )
        VotingService.cast_parameter_vote(
            data["user1"], round, mrl_vote="increase", rtm_vote="no_change"
        )
        VotingService.cast_parameter_vote(
            data["user2"], round, mrl_vote="no_change", rtm_vote="decrease"
        )

        mrl_counts = VotingService.count_votes(round, "mrl")
        rtm_counts = VotingService.count_votes(round, "rtm")

        # MRL: 2 increase, 1 no_change, 0 decrease
        assert mrl_counts["increase"] == 2
        assert mrl_counts["no_change"] == 1
        assert mrl_counts["decrease"] == 0
        assert mrl_counts["not_voted"] == 0
        assert mrl_counts["total_eligible"] == 3

        # RTM: 0 increase, 1 no_change, 2 decrease
        assert rtm_counts["increase"] == 0
        assert rtm_counts["no_change"] == 1
        assert rtm_counts["decrease"] == 2

    def test_abstention_as_no_change(self, setup_voting_scenario):
        """Abstentions count as 'no_change'"""
        data = setup_voting_scenario
        round = data["round"]

        # Only 1 person votes
        VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="increase"
        )

        # Resolve with abstentions
        mrl_result = VotingService.resolve_vote(round, "mrl")

        # 1 increase, 2 abstentions (count as no_change)
        # no_change should win
        assert mrl_result == "no_change"

    def test_tie_goes_to_no_change(self, setup_voting_scenario):
        """In a tie, 'no_change' wins"""
        data = setup_voting_scenario
        round = data["round"]

        # Create a tie: 1 increase, 1 decrease, 1 abstention (no_change)
        VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="increase"
        )
        VotingService.cast_parameter_vote(
            data["user1"], round, mrl_vote="decrease", rtm_vote="decrease"
        )
        # user2 doesn't vote (abstention = no_change)

        mrl_result = VotingService.resolve_vote(round, "mrl")

        # With abstentions: 1 increase, 1 effective no_change, 1 decrease
        # All tied - no_change wins ties
        assert mrl_result == "no_change"

    def test_apply_parameter_increase(self, setup_voting_scenario):
        """Apply parameter increase (20% increment)"""
        data = setup_voting_scenario
        discussion = data["discussion"]
        config = data["config"]

        original_mrl = discussion.max_response_length_chars

        VotingService.apply_parameter_change(discussion, "mrl", "increase", config)

        discussion.refresh_from_db()

        # Should be 20% higher
        expected = int(original_mrl * 1.20)
        assert discussion.max_response_length_chars == expected

    def test_apply_parameter_decrease(self, setup_voting_scenario):
        """Apply parameter decrease (20% decrement)"""
        data = setup_voting_scenario
        discussion = data["discussion"]
        config = data["config"]

        original_rtm = discussion.response_time_multiplier

        VotingService.apply_parameter_change(discussion, "rtm", "decrease", config)

        discussion.refresh_from_db()

        # Should be 20% lower
        expected = original_rtm * 0.80
        assert abs(discussion.response_time_multiplier - expected) < 0.01

    def test_parameter_bounds_validation(self, setup_voting_scenario):
        """Parameter changes respect min/max bounds"""
        data = setup_voting_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set MRL near max
        discussion.max_response_length_chars = config.mrl_max_chars
        discussion.save()

        VotingService.apply_parameter_change(discussion, "mrl", "increase", config)

        discussion.refresh_from_db()

        # Should not exceed max
        assert discussion.max_response_length_chars <= config.mrl_max_chars

    def test_voting_window_expiration(self, setup_voting_scenario):
        """Test voting window closes and applies changes"""
        data = setup_voting_scenario
        round = data["round"]
        config = data["config"]

        # Cast votes
        VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="decrease"
        )
        VotingService.cast_parameter_vote(
            data["user1"], round, mrl_vote="increase", rtm_vote="decrease"
        )

        # Start voting
        VotingService.start_voting_window(round)
        assert round.status == "voting"

        # Close voting
        VotingService.close_voting_window(round, config)

        round.refresh_from_db()
        assert round.status == "completed"

        # Parameters should be updated
        discussion = round.discussion
        discussion.refresh_from_db()

        # MRL increased, RTM decreased
        assert discussion.max_response_length_chars > 1000
        assert discussion.response_time_multiplier < 1.0

    def test_multiple_independent_votes(self, setup_voting_scenario):
        """MRL and RTM votes are independent"""
        data = setup_voting_scenario
        round = data["round"]

        # User can vote differently for each parameter
        vote = VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="decrease"
        )

        assert vote.mrl_vote == "increase"
        assert vote.rtm_vote == "decrease"

        # Resolve each independently with only one vote
        # Both will be 'no_change' because abstentions count as no_change
        # and with only 1 vote out of 3 eligible, no_change wins
        mrl_result = VotingService.resolve_vote(round, "mrl")
        rtm_result = VotingService.resolve_vote(round, "rtm")

        # With abstentions, both default to no_change in this scenario
        # But the votes themselves are different
        assert vote.mrl_vote != vote.rtm_vote

    def test_update_existing_vote(self, setup_voting_scenario):
        """User can update their vote"""
        data = setup_voting_scenario
        round = data["round"]

        # Cast initial vote
        vote1 = VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="increase", rtm_vote="increase"
        )

        # Update vote
        vote2 = VotingService.cast_parameter_vote(
            data["initiator"], round, mrl_vote="decrease", rtm_vote="decrease"
        )

        # Should be same vote object, updated
        assert vote1.id == vote2.id
        assert vote2.mrl_vote == "decrease"
        assert vote2.rtm_vote == "decrease"

    def test_vote_counts_displayed_in_ui(self, setup_voting_scenario):
        """Verify vote counts visible during voting"""
        from core.models import JoinRequest

        data = setup_voting_scenario
        round = data["round"]
        discussion = data["discussion"]

        # Create join request
        requester = User.objects.create_user(
            username="requester", phone_number="+11234567894", password="test123"
        )
        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=data["initiator"],
            status='pending'
        )

        # Cast some votes
        VotingService.record_join_request_vote(
            round_obj=round,
            voter=data["initiator"],
            join_request=join_request,
            approve=True
        )
        VotingService.record_join_request_vote(
            round_obj=round,
            voter=data["user1"],
            join_request=join_request,
            approve=False
        )

        # Get vote counts
        counts = VotingService.get_join_request_vote_counts(round, join_request)

        # Verify counts are available (would be displayed in UI)
        assert counts is not None
        assert 'approve' in counts
        assert 'deny' in counts
        assert 'total' in counts
        assert counts['approve'] == 1
        assert counts['deny'] == 1
        assert counts['total'] == 2

    def test_multiple_join_requests_processed(self, setup_voting_scenario):
        """Verify batch processing works for multiple join requests"""
        from core.models import JoinRequest

        data = setup_voting_scenario
        round = data["round"]
        discussion = data["discussion"]

        # Create multiple join requests
        requester1 = User.objects.create_user(
            username="requester1", phone_number="+11234567894", password="test123"
        )
        requester2 = User.objects.create_user(
            username="requester2", phone_number="+11234567895", password="test123"
        )
        requester3 = User.objects.create_user(
            username="requester3", phone_number="+11234567896", password="test123"
        )

        join_request1 = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester1,
            approver=data["initiator"],
            status='pending'
        )
        join_request2 = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester2,
            approver=data["initiator"],
            status='pending'
        )
        join_request3 = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester3,
            approver=data["initiator"],
            status='pending'
        )

        # Vote on multiple requests with different outcomes
        # Request 1: Approve (2 yes, 1 no = 66% approval)
        VotingService.record_join_request_vote(round, data["initiator"], join_request1, True)
        VotingService.record_join_request_vote(round, data["user1"], join_request1, True)
        VotingService.record_join_request_vote(round, data["user2"], join_request1, False)

        # Request 2: Deny (1 yes, 2 no = 33% approval)
        VotingService.record_join_request_vote(round, data["initiator"], join_request2, True)
        VotingService.record_join_request_vote(round, data["user1"], join_request2, False)
        VotingService.record_join_request_vote(round, data["user2"], join_request2, False)

        # Request 3: No votes (stays pending)

        # Process all join requests
        results = VotingService.process_join_request_votes(round)

        # Verify batch processing
        assert len(results['approved']) == 1
        assert join_request1 in results['approved']

        assert len(results['denied']) == 1
        assert join_request2 in results['denied']

        assert len(results['pending']) == 1
        assert join_request3 in results['pending']

        # Verify database updates
        join_request1.refresh_from_db()
        join_request2.refresh_from_db()
        join_request3.refresh_from_db()

        assert join_request1.status == 'approved'
        assert join_request2.status == 'declined'
        assert join_request3.status == 'pending'
