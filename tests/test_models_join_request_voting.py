"""
Tests for JoinRequestVote model and voting_credits_awarded field.

Added: 2026-02 to test voting-based join request approval mechanics.
"""

import pytest
from django.db import IntegrityError
from django.test import TestCase
from core.models import JoinRequestVote, Round, JoinRequest, User, Discussion, DiscussionParticipant
from tests.factories import UserFactory, DiscussionFactory, RoundFactory, JoinRequestFactory


class JoinRequestVoteModelTest(TestCase):
    """Test JoinRequestVote model functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.initiator = UserFactory()
        self.requester = UserFactory()
        self.voter = UserFactory()
        self.discussion = DiscussionFactory(initiator=self.initiator)
        self.round = RoundFactory(discussion=self.discussion, round_number=1)
        self.join_request = JoinRequestFactory(
            discussion=self.discussion,
            requester=self.requester,
            approver=self.initiator
        )

    def test_join_request_vote_creation(self):
        """Test that JoinRequestVote can be created with all fields."""
        vote = JoinRequestVote.objects.create(
            round=self.round,
            voter=self.voter,
            join_request=self.join_request,
            approve=True
        )

        self.assertIsNotNone(vote.id)
        self.assertEqual(vote.round, self.round)
        self.assertEqual(vote.voter, self.voter)
        self.assertEqual(vote.join_request, self.join_request)
        self.assertTrue(vote.approve)
        self.assertIsNotNone(vote.voted_at)

        # Test string representation
        expected_str = f"{self.voter.username} votes approve for {self.join_request}"
        self.assertEqual(str(vote), expected_str)

        # Test deny vote
        voter2 = UserFactory()
        deny_vote = JoinRequestVote.objects.create(
            round=self.round,
            voter=voter2,
            join_request=self.join_request,
            approve=False
        )
        expected_deny_str = f"{voter2.username} votes deny for {self.join_request}"
        self.assertEqual(str(deny_vote), expected_deny_str)

    def test_join_request_vote_unique_constraint(self):
        """Test that voter can't vote twice on same request in same round."""
        from django.db import transaction

        # Create first vote
        JoinRequestVote.objects.create(
            round=self.round,
            voter=self.voter,
            join_request=self.join_request,
            approve=True
        )

        # Try to create duplicate vote in an atomic block
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                JoinRequestVote.objects.create(
                    round=self.round,
                    voter=self.voter,
                    join_request=self.join_request,
                    approve=False
                )

        # Verify only one vote exists
        votes = JoinRequestVote.objects.filter(
            round=self.round,
            voter=self.voter,
            join_request=self.join_request
        )
        self.assertEqual(votes.count(), 1)

        # Verify same voter CAN vote on different request
        join_request2 = JoinRequestFactory(
            discussion=self.discussion,
            requester=UserFactory(),
            approver=self.initiator
        )
        vote2 = JoinRequestVote.objects.create(
            round=self.round,
            voter=self.voter,
            join_request=join_request2,
            approve=True
        )
        self.assertIsNotNone(vote2.id)

        # Verify same voter CAN vote on same request in different round
        round2 = RoundFactory(discussion=self.discussion, round_number=2)
        vote3 = JoinRequestVote.objects.create(
            round=round2,
            voter=self.voter,
            join_request=self.join_request,
            approve=False
        )
        self.assertIsNotNone(vote3.id)

    def test_join_request_vote_cascading_delete(self):
        """Test that votes are deleted when round/user/request deleted."""
        vote = JoinRequestVote.objects.create(
            round=self.round,
            voter=self.voter,
            join_request=self.join_request,
            approve=True
        )
        vote_id = vote.id

        # Test cascade on round deletion
        self.round.delete()
        self.assertFalse(JoinRequestVote.objects.filter(id=vote_id).exists())

        # Set up new fixtures for next test
        round2 = RoundFactory(discussion=self.discussion, round_number=2)
        vote2 = JoinRequestVote.objects.create(
            round=round2,
            voter=self.voter,
            join_request=self.join_request,
            approve=True
        )
        vote2_id = vote2.id

        # Test cascade on voter deletion
        self.voter.delete()
        self.assertFalse(JoinRequestVote.objects.filter(id=vote2_id).exists())

        # Set up new fixtures for next test
        voter3 = UserFactory()
        vote3 = JoinRequestVote.objects.create(
            round=round2,
            voter=voter3,
            join_request=self.join_request,
            approve=True
        )
        vote3_id = vote3.id

        # Test cascade on join_request deletion
        self.join_request.delete()
        self.assertFalse(JoinRequestVote.objects.filter(id=vote3_id).exists())

    def test_round_voting_credits_awarded_default(self):
        """Test that Round.voting_credits_awarded defaults to empty list."""
        round = RoundFactory(discussion=self.discussion, round_number=3)

        # Check default value
        self.assertEqual(round.voting_credits_awarded, [])
        self.assertIsInstance(round.voting_credits_awarded, list)

    def test_round_voting_credits_awarded_tracking(self):
        """Test that we can add and check user IDs in voting_credits_awarded list."""
        round = RoundFactory(discussion=self.discussion, round_number=4)

        # Initially empty
        self.assertEqual(round.voting_credits_awarded, [])

        # Add first user ID
        user1 = UserFactory()
        round.voting_credits_awarded.append(str(user1.id))
        round.save()
        round.refresh_from_db()

        self.assertIn(str(user1.id), round.voting_credits_awarded)
        self.assertEqual(len(round.voting_credits_awarded), 1)

        # Add second user ID
        user2 = UserFactory()
        round.voting_credits_awarded.append(str(user2.id))
        round.save()
        round.refresh_from_db()

        self.assertIn(str(user1.id), round.voting_credits_awarded)
        self.assertIn(str(user2.id), round.voting_credits_awarded)
        self.assertEqual(len(round.voting_credits_awarded), 2)

        # Test checking if user already received credits
        self.assertTrue(str(user1.id) in round.voting_credits_awarded)
        self.assertTrue(str(user2.id) in round.voting_credits_awarded)

        user3 = UserFactory()
        self.assertFalse(str(user3.id) in round.voting_credits_awarded)

    def test_join_request_vote_indexes(self):
        """Test that indexes exist for performance."""
        # This test verifies the model meta configuration
        # The actual index creation is handled by migrations

        # Get model meta
        meta = JoinRequestVote._meta

        # Verify indexes are defined
        index_names = [index.name for index in meta.indexes]

        self.assertIn('idx_jrv_round_request', index_names)
        self.assertIn('idx_jrv_voter_time', index_names)

        # Verify unique_together constraint (Django returns tuple of tuples)
        self.assertIn(('round', 'voter', 'join_request'), meta.unique_together)

        # Create some votes to ensure the indexes work in queries
        voter1 = UserFactory()
        voter2 = UserFactory()

        vote1 = JoinRequestVote.objects.create(
            round=self.round,
            voter=voter1,
            join_request=self.join_request,
            approve=True
        )

        vote2 = JoinRequestVote.objects.create(
            round=self.round,
            voter=voter2,
            join_request=self.join_request,
            approve=False
        )

        # Query using indexed fields
        votes_for_request = JoinRequestVote.objects.filter(
            round=self.round,
            join_request=self.join_request
        )
        self.assertEqual(votes_for_request.count(), 2)

        votes_by_voter = JoinRequestVote.objects.filter(voter=voter1).order_by('-voted_at')
        self.assertEqual(votes_by_voter.count(), 1)
        self.assertEqual(votes_by_voter.first(), vote1)
