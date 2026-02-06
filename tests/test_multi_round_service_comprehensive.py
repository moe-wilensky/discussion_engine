"""
Comprehensive integration tests for MultiRoundService.

Focus: Achieve 85%+ coverage of multi_round_service.py
Current: 0% → Target: 85%+

Tests cover round lifecycle, termination conditions, and archival logic.
"""
from decimal import Decimal
from datetime import timedelta
import pytest
from django.test import TransactionTestCase
from django.utils import timezone
from core.models import (
    Discussion, Round, User, DiscussionParticipant,
    PlatformConfig, Response, Vote, JoinRequest, JoinRequestVote
)
from core.services.multi_round_service import MultiRoundService
from tests.factories import UserFactory, DiscussionFactory


class MultiRoundServiceIntegrationTests(TransactionTestCase):
    """
    Integration tests for MultiRoundService.

    Tests the round lifecycle management including:
    - Creating next rounds
    - Checking termination conditions
    - Archiving discussions
    - Complete round transition workflow
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
                'rtm_max': 3.0,
                'max_discussion_duration_days': 30,
                'max_discussion_rounds': 10,
                'max_discussion_responses': 100
            }
        )

        # Create users
        self.users = []
        for i in range(5):
            user = UserFactory.create(
                username=f'round_user{i}',
                email=f'round_user{i}@test.com',
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
            topic_headline='Multi-Round Test Discussion',
            topic_details='Testing round lifecycle',
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

        # Create initial round
        self.round1 = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            status='voting',
            start_time=timezone.now() - timedelta(days=1),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

    # Test create_next_round
    def test_create_next_round_success(self):
        """Test successfully creating next round."""
        # Create some responses so termination condition isn't met
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,  # Make it long enough
                is_draft=False
            )

        next_round = MultiRoundService.create_next_round(
            self.discussion,
            self.round1
        )

        assert next_round is not None
        assert next_round.round_number == 2
        assert next_round.status == 'in_progress'
        assert next_round.final_mrp_minutes == self.round1.final_mrp_minutes

    def test_create_next_round_inherits_mrp(self):
        """Test next round inherits MRP from previous round."""
        # Create responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Set specific MRP
        self.round1.final_mrp_minutes = 45
        self.round1.save()

        next_round = MultiRoundService.create_next_round(
            self.discussion,
            self.round1
        )

        assert next_round.final_mrp_minutes == 45

    def test_create_next_round_archives_if_termination_met(self):
        """Test round creation archives discussion if termination condition met."""
        # Create only 1 response (termination condition)
        Response.objects.create(
            round=self.round1,
            user=self.users[0],
            content='Test response ' * 20,
            is_draft=False
        )

        next_round = MultiRoundService.create_next_round(
            self.discussion,
            self.round1
        )

        assert next_round is None
        self.discussion.refresh_from_db()
        assert self.discussion.status == 'archived'
        assert self.discussion.archived_at is not None

    # Test check_termination_conditions
    def test_check_termination_all_permanent_observers(self):
        """Test termination when all active participants become permanent observers."""
        # Create responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Make all participants permanent observers
        DiscussionParticipant.objects.filter(
            discussion=self.discussion
        ).update(role='permanent_observer')

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert 'permanent observers' in reason.lower()

    def test_check_termination_one_response(self):
        """Test termination when round has only 1 response."""
        # Create only 1 response
        Response.objects.create(
            round=self.round1,
            user=self.users[0],
            content='Test response ' * 20,
            is_draft=False
        )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert '1 response' in reason

    def test_check_termination_zero_responses(self):
        """Test termination when round has 0 responses."""
        # No responses created

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert '0 response' in reason

    def test_check_termination_duration_exceeded(self):
        """Test termination when max duration exceeded."""
        # Create enough responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Set discussion creation to 31 days ago (config max is 30)
        self.discussion.created_at = timezone.now() - timedelta(days=31)
        self.discussion.save()

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert 'duration' in reason.lower()
        assert '30' in reason

    def test_check_termination_max_rounds_reached(self):
        """Test termination when max rounds reached."""
        # Create enough responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Set round number to max (config max is 10)
        self.round1.round_number = 10
        self.round1.save()

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert 'maximum rounds' in reason.lower()
        assert '10' in reason

    def test_check_termination_max_responses_reached(self):
        """Test termination when max total responses reached."""
        # Create 100 responses (config max is 100)
        # We'll cheat and just create enough to trigger
        for i in range(100):
            Response.objects.create(
                round=self.round1,
                user=self.users[i % 3],
                content=f'Test response {i} ' * 20,
                is_draft=False
            )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        assert 'maximum responses' in reason.lower()
        assert '100' in reason

    def test_check_termination_no_conditions_met(self):
        """Test no termination when all conditions pass."""
        # Create enough responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Ensure all limits not reached
        self.discussion.created_at = timezone.now() - timedelta(days=5)
        self.discussion.save()
        self.round1.round_number = 3
        self.round1.save()

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is False
        assert reason is None

    def test_check_termination_disabled_limits_not_checked(self):
        """Test termination conditions disabled when config values are 0."""
        # Create enough responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Disable all limits
        self.config.max_discussion_duration_days = 0
        self.config.max_discussion_rounds = 0
        self.config.max_discussion_responses = 0
        self.config.save()

        # Set extreme values
        self.discussion.created_at = timezone.now() - timedelta(days=365)
        self.discussion.save()
        self.round1.round_number = 100
        self.round1.save()

        # Should still not archive (limits disabled)
        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is False
        assert reason is None

    # Test archive_discussion
    def test_archive_discussion(self):
        """Test archiving discussion."""
        # Create some responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        initial_status = self.discussion.status

        MultiRoundService.archive_discussion(self.discussion, 'Test archival')

        self.discussion.refresh_from_db()
        assert self.discussion.status == 'archived'
        assert self.discussion.archived_at is not None
        assert initial_status != 'archived'

    def test_archive_discussion_locks_all_responses(self):
        """Test archiving locks all responses across all rounds."""
        # Create multiple rounds with responses
        round2 = Round.objects.create(
            discussion=self.discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now(),
            final_mrp_minutes=30,
            voting_credits_awarded=[]
        )

        response1 = Response.objects.create(
            round=self.round1,
            user=self.users[0],
            content='Response in round 1 ' * 20,
            is_draft=False
        )
        response2 = Response.objects.create(
            round=self.round1,
            user=self.users[1],
            content='Response in round 1 ' * 20,
            is_draft=False
        )
        response3 = Response.objects.create(
            round=round2,
            user=self.users[0],
            content='Response in round 2 ' * 20,
            is_draft=False
        )

        MultiRoundService.archive_discussion(self.discussion, 'Test archival')

        # Check all responses locked
        response1.refresh_from_db()
        response2.refresh_from_db()
        response3.refresh_from_db()

        assert response1.is_locked is True
        assert response2.is_locked is True
        assert response3.is_locked is True

    # Test close_voting_and_create_next_round
    def test_close_voting_and_create_next_round_processes_parameter_votes(self):
        """Test closing voting processes parameter votes and updates discussion."""
        # Create responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Create parameter votes
        for i in range(3):
            Vote.objects.create(
                round=self.round1,
                user=self.users[i],
                mrl_vote='increase',
                rtm_vote='no_change'
            )

        initial_mrl = self.discussion.max_response_length_chars

        next_round = MultiRoundService.close_voting_and_create_next_round(
            self.round1
        )

        assert next_round is not None
        self.discussion.refresh_from_db()
        # MRL should have increased
        assert self.discussion.max_response_length_chars > initial_mrl

    def test_close_voting_and_create_next_round_processes_join_requests(self):
        """Test closing voting processes join request votes."""
        # Create responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        # Create join request
        join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.users[4],
            status='pending'
        )

        # Create approval votes (majority approve)
        for i in range(3):
            JoinRequestVote.objects.create(
                round=self.round1,
                voter=self.users[i],
                join_request=join_request,
                approve=True
            )

        next_round = MultiRoundService.close_voting_and_create_next_round(
            self.round1
        )

        assert next_round is not None
        join_request.refresh_from_db()
        # Join request should be approved
        assert join_request.status == 'approved'

    def test_close_voting_and_create_next_round_returns_next_round(self):
        """Test closing voting returns the new round."""
        # Create responses
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        next_round = MultiRoundService.close_voting_and_create_next_round(
            self.round1
        )

        assert next_round is not None
        assert isinstance(next_round, Round)
        assert next_round.round_number == self.round1.round_number + 1
        assert next_round.discussion == self.discussion

    def test_close_voting_and_create_next_round_no_next_round_if_archived(self):
        """Test closing voting returns None if discussion archived."""
        # Create only 1 response (triggers termination)
        Response.objects.create(
            round=self.round1,
            user=self.users[0],
            content='Test response ' * 20,
            is_draft=False
        )

        next_round = MultiRoundService.close_voting_and_create_next_round(
            self.round1
        )

        # Should return None because discussion archived
        assert next_round is None
        self.discussion.refresh_from_db()
        assert self.discussion.status == 'archived'

    def test_create_next_round_sequential_numbering(self):
        """Test rounds are numbered sequentially."""
        # Create multiple rounds
        for i in range(3):
            Response.objects.create(
                round=self.round1,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        round2 = MultiRoundService.create_next_round(self.discussion, self.round1)
        assert round2.round_number == 2

        # Create responses for round 2
        for i in range(3):
            Response.objects.create(
                round=round2,
                user=self.users[i],
                content='Test response ' * 20,
                is_draft=False
            )

        round3 = MultiRoundService.create_next_round(self.discussion, round2)
        assert round3.round_number == 3

    def test_check_termination_prioritizes_permanent_observers(self):
        """Test permanent observers condition checked first."""
        # Create only 1 response AND make all permanent observers
        Response.objects.create(
            round=self.round1,
            user=self.users[0],
            content='Test response ' * 20,
            is_draft=False
        )

        DiscussionParticipant.objects.filter(
            discussion=self.discussion
        ).update(role='permanent_observer')

        should_archive, reason = MultiRoundService.check_termination_conditions(
            self.discussion,
            self.round1,
            self.config
        )

        assert should_archive is True
        # Should be permanent observers, not response count
        assert 'permanent observers' in reason.lower()
        assert 'response' not in reason.lower()

    def test_archive_discussion_sets_timestamp(self):
        """Test archiving sets archived_at timestamp."""
        before_archive = timezone.now()

        MultiRoundService.archive_discussion(self.discussion, 'Test')

        self.discussion.refresh_from_db()
        assert self.discussion.archived_at is not None
        assert self.discussion.archived_at >= before_archive
        # Allow 1 second tolerance
        assert (self.discussion.archived_at - before_archive).total_seconds() < 1
