"""
Integration tests for complete voting workflows including join requests.
"""
import pytest
from django.test import TestCase
from core.models import User, Discussion, Round, JoinRequest, DiscussionParticipant
from core.services.voting_service import VotingService
from core.services.multi_round_service import MultiRoundService
from tests.factories import UserFactory, DiscussionFactory, RoundFactory


@pytest.mark.django_db
class TestVotingIntegrationTests:
    """Test complete voting workflows."""

    def test_complete_voting_phase_with_join_requests(self):
        """Test full voting phase including join request processing."""
        from core.models import Response

        # Set up discussion with 3 active participants
        initiator = UserFactory(username='init')
        user1 = UserFactory(username='user1')
        user2 = UserFactory(username='user2')

        discussion = DiscussionFactory(
            initiator=initiator,
            max_response_length_chars=1000,
            min_response_time_minutes=30
        )

        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='in_progress'
        )

        # Add other participants
        for user in [user1, user2]:
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=user,
                role='active'
            )

        # Users post responses (needed for voting eligibility)
        Response.objects.create(user=initiator, round=round1, content='Response 1', character_count=11)
        Response.objects.create(user=user1, round=round1, content='Response 2', character_count=11)
        Response.objects.create(user=user2, round=round1, content='Response 3', character_count=11)

        # Change to voting status
        round1.status = 'voting'
        round1.save()

        # Create join request
        requester = UserFactory(username='requester')
        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator,
            request_message='Please let me join',
            status='pending'
        )

        # Users vote on parameters
        VotingService.cast_parameter_vote(initiator, round1, 'increase', 'no_change')
        VotingService.cast_parameter_vote(user1, round1, 'no_change', 'decrease')

        # Users vote on join request (2 approve, 1 deny = majority approve)
        VotingService.record_join_request_vote(round1, initiator, join_request, True)
        VotingService.record_join_request_vote(round1, user1, join_request, True)
        VotingService.record_join_request_vote(round1, user2, join_request, False)

        # Close voting and create next round
        round2 = MultiRoundService.close_voting_and_create_next_round(round1)

        # Verify join request was approved
        join_request.refresh_from_db()
        assert join_request.status == 'approved'

        # Verify requester is now participant
        participation = DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester,
            role='active'
        ).exists()
        assert participation

        # Verify all voters received credits (once each)
        for user in [initiator, user1, user2]:
            user.refresh_from_db()
            # Each should have earned credits from voting
            assert user.platform_invites_acquired > 0
            assert user.discussion_invites_acquired > 0

    def test_join_request_denied_by_majority(self):
        """Test join request denial when majority votes no."""
        from core.models import Response

        # Set up similar to above but with 2 deny votes
        initiator = UserFactory(username='init')
        user1 = UserFactory(username='user1')
        user2 = UserFactory(username='user2')

        discussion = DiscussionFactory(initiator=initiator)

        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='in_progress'
        )

        # Add other participants
        for user in [user1, user2]:
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=user,
                role='active'
            )

        # Users post responses (needed for voting eligibility)
        Response.objects.create(user=initiator, round=round1, content='Response 1', character_count=11)
        Response.objects.create(user=user1, round=round1, content='Response 2', character_count=11)
        Response.objects.create(user=user2, round=round1, content='Response 3', character_count=11)

        # Change to voting status
        round1.status = 'voting'
        round1.save()

        # Create join request
        requester = UserFactory(username='requester')
        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator,
            request_message='Please let me join',
            status='pending'
        )

        # 2 users deny, 1 approves
        VotingService.record_join_request_vote(round1, user1, join_request, False)
        VotingService.record_join_request_vote(round1, user2, join_request, False)
        VotingService.record_join_request_vote(round1, initiator, join_request, True)

        # Process votes
        MultiRoundService.close_voting_and_create_next_round(round1)

        # Verify request denied (status is 'declined' not 'denied')
        join_request.refresh_from_db()
        assert join_request.status == 'declined'

    def test_join_request_stays_pending_on_tie(self):
        """Test join request stays pending on 50/50 tie."""
        # Set up with 2 users
        initiator = UserFactory(username='init')
        user1 = UserFactory(username='user1')

        discussion = DiscussionFactory(initiator=initiator)

        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status='voting'
        )

        # Add other participant
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user1,
            role='active'
        )

        # Create join request
        requester = UserFactory(username='requester')
        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator,
            request_message='Please let me join',
            status='pending'
        )

        # 1 approves, 1 denies = 50/50 tie
        VotingService.record_join_request_vote(round1, user1, join_request, True)
        VotingService.record_join_request_vote(round1, initiator, join_request, False)

        # Process votes
        MultiRoundService.close_voting_and_create_next_round(round1)

        # Verify request still pending
        join_request.refresh_from_db()
        assert join_request.status == 'pending'
