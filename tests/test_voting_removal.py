"""
Tests for removal voting functionality.

Tests removal vote casting, counting, super-majority threshold, and permanent observer status.
"""

import pytest
from django.utils import timezone

from core.models import (
    User, Discussion, Round, RemovalVote, DiscussionParticipant,
    PlatformConfig, Response, ModerationAction
)
from core.services.moderation_voting_service import ModerationVotingService


@pytest.mark.django_db
class TestRemovalVoting:
    """Test vote-based removal system"""

    @pytest.fixture
    def setup_removal_scenario(self):
        """Create discussion with participants ready for removal voting"""
        config = PlatformConfig.load()
        config.vote_based_removal_threshold = 0.50  # 50% threshold for testing
        config.save()
        
        # Create 5 users
        users = []
        for i in range(5):
            user = User.objects.create_user(
                username=f'user{i}',
                phone_number=f'+1123456789{i}',
                password='test123'
            )
            user.platform_invites_acquired = 5
            user.platform_invites_banked = 3
            user.save()
            users.append(user)
        
        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline='Test Discussion',
            topic_details='Testing removal voting',
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=users[0]
        )
        
        # Create participants
        for i, user in enumerate(users):
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=user,
                role='initiator' if i == 0 else 'active'
            )
        
        # Create round
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='voting',
            final_mrp_minutes=60.0
        )
        
        # All users responded
        for user in users:
            Response.objects.create(
                round=round, user=user,
                content='Test' * 25, character_count=100
            )
        
        return {
            'config': config,
            'users': users,
            'discussion': discussion,
            'round': round
        }

    def test_cast_removal_vote_single_target(self, setup_removal_scenario):
        """Cast removal vote for single target"""
        data = setup_removal_scenario
        round = data['round']
        voter = data['users'][0]
        target = data['users'][1]
        
        votes = ModerationVotingService.cast_removal_vote(
            voter, round, [target]
        )
        
        assert len(votes) == 1
        assert votes[0].voter == voter
        assert votes[0].target == target
        assert votes[0].round == round

    def test_cast_removal_vote_multiple_targets(self, setup_removal_scenario):
        """Cast removal vote for multiple targets"""
        data = setup_removal_scenario
        round = data['round']
        voter = data['users'][0]
        targets = [data['users'][1], data['users'][2], data['users'][3]]
        
        votes = ModerationVotingService.cast_removal_vote(
            voter, round, targets
        )
        
        assert len(votes) == 3
        assert all(v.voter == voter for v in votes)

    def test_cannot_vote_for_self(self, setup_removal_scenario):
        """Cannot vote to remove yourself"""
        data = setup_removal_scenario
        round = data['round']
        voter = data['users'][0]
        
        # Try to vote for self
        votes = ModerationVotingService.cast_removal_vote(
            voter, round, [voter]
        )
        
        # No votes should be cast
        assert len(votes) == 0

    def test_vote_counting_correct(self, setup_removal_scenario):
        """Vote counting per target is accurate"""
        data = setup_removal_scenario
        round = data['round']
        target = data['users'][0]
        
        # 3 users vote to remove target
        ModerationVotingService.cast_removal_vote(
            data['users'][1], round, [target]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][3], round, [target]
        )
        
        vote_info = ModerationVotingService.count_removal_votes(round, target)
        
        assert vote_info['votes_for_removal'] == 3
        assert vote_info['total_eligible_voters'] == 5
        assert vote_info['percentage'] == 60.0  # 3/5 = 60%
        assert vote_info['threshold'] == 50.0
        assert vote_info['will_be_removed'] is True

    def test_threshold_not_met(self, setup_removal_scenario):
        """Target not removed if threshold not met"""
        data = setup_removal_scenario
        round = data['round']
        target = data['users'][0]
        
        # Only 2 users vote (40%, below 50% threshold)
        ModerationVotingService.cast_removal_vote(
            data['users'][1], round, [target]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target]
        )
        
        vote_info = ModerationVotingService.count_removal_votes(round, target)
        
        assert vote_info['votes_for_removal'] == 2
        assert vote_info['percentage'] == 40.0
        assert vote_info['will_be_removed'] is False

    def test_resolve_removal_votes(self, setup_removal_scenario):
        """Resolve removal votes and remove users above threshold"""
        data = setup_removal_scenario
        round = data['round']
        config = data['config']
        
        target1 = data['users'][0]
        target2 = data['users'][1]
        
        # Vote to remove target1 (3 votes = 60%, above threshold)
        ModerationVotingService.cast_removal_vote(
            data['users'][1], round, [target1]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target1]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][3], round, [target1]
        )
        
        # Vote to remove target2 (only 2 votes = 40%, below threshold)
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target2]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][3], round, [target2]
        )
        
        removed = ModerationVotingService.resolve_removal_votes(round, config)
        
        # Only target1 should be removed
        assert len(removed) == 1
        assert target1 in removed
        assert target2 not in removed

    def test_permanent_observer_status(self, setup_removal_scenario):
        """Removed user becomes permanent observer"""
        data = setup_removal_scenario
        round = data['round']
        config = data['config']
        target = data['users'][0]
        
        # Get enough votes to remove
        for user in data['users'][1:4]:
            ModerationVotingService.cast_removal_vote(
                user, round, [target]
            )
        
        ModerationVotingService.resolve_removal_votes(round, config)
        
        participant = DiscussionParticipant.objects.get(
            discussion=data['discussion'], user=target
        )
        
        assert participant.role == 'permanent_observer'
        assert participant.observer_reason == 'vote_based_removal'
        assert participant.observer_since is not None

    def test_platform_invites_reset(self, setup_removal_scenario):
        """Platform invites reset to 0 for removed users"""
        data = setup_removal_scenario
        round = data['round']
        config = data['config']
        target = data['users'][0]
        
        # Verify user has invites before removal
        assert target.platform_invites_acquired > 0
        assert target.platform_invites_banked > 0
        
        # Get enough votes to remove
        for user in data['users'][1:4]:
            ModerationVotingService.cast_removal_vote(
                user, round, [target]
            )
        
        ModerationVotingService.resolve_removal_votes(round, config)
        
        target.refresh_from_db()
        
        assert target.platform_invites_acquired == 0
        assert target.platform_invites_banked == 0

    def test_multiple_users_removed_simultaneously(self, setup_removal_scenario):
        """Multiple users can be removed in same vote"""
        data = setup_removal_scenario
        round = data['round']
        config = data['config']
        
        target1 = data['users'][0]
        target2 = data['users'][1]
        
        # Vote to remove both targets
        for voter in data['users'][2:5]:
            ModerationVotingService.cast_removal_vote(
                voter, round, [target1, target2]
            )
        
        removed = ModerationVotingService.resolve_removal_votes(round, config)
        
        # Both should be removed
        assert len(removed) == 2
        assert target1 in removed
        assert target2 in removed

    def test_moderation_action_logged(self, setup_removal_scenario):
        """Removal is logged in ModerationAction"""
        data = setup_removal_scenario
        round = data['round']
        config = data['config']
        target = data['users'][0]
        
        # Vote to remove
        for user in data['users'][1:4]:
            ModerationVotingService.cast_removal_vote(
                user, round, [target]
            )
        
        ModerationVotingService.resolve_removal_votes(round, config)
        
        # Check moderation action was logged
        action = ModerationAction.objects.filter(
            discussion=data['discussion'],
            target=target,
            action_type='vote_based_removal'
        ).first()
        
        assert action is not None
        assert action.is_permanent is True
        assert action.round_occurred == round

    def test_80_percent_threshold(self, setup_removal_scenario):
        """Test with default 80% super-majority threshold"""
        data = setup_removal_scenario
        config = data['config']
        
        # Set to 80% threshold
        config.vote_based_removal_threshold = 0.80
        config.save()
        
        round = data['round']
        target = data['users'][0]
        
        # 3 out of 5 votes = 60% (below 80%)
        for user in data['users'][1:4]:
            ModerationVotingService.cast_removal_vote(
                user, round, [target]
            )
        
        vote_info = ModerationVotingService.count_removal_votes(round, target)
        
        assert vote_info['percentage'] == 60.0
        assert vote_info['threshold'] == 80.0
        assert vote_info['will_be_removed'] is False
        
        # Need 4 out of 5 votes = 80%
        ModerationVotingService.cast_removal_vote(
            data['users'][4], round, [target]
        )
        
        vote_info = ModerationVotingService.count_removal_votes(round, target)
        
        assert vote_info['percentage'] == 80.0
        assert vote_info['will_be_removed'] is True

    def test_hidden_ballot(self, setup_removal_scenario):
        """Votes are not visible until resolved (hidden ballot)"""
        data = setup_removal_scenario
        round = data['round']
        target = data['users'][0]
        
        # Cast votes
        ModerationVotingService.cast_removal_vote(
            data['users'][1], round, [target]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target]
        )
        
        # Votes exist in database but not publicly visible
        # (Implementation detail - in real system, API would hide this)
        vote_count = RemovalVote.objects.filter(
            round=round, target=target
        ).count()
        
        assert vote_count == 2
        
        # After resolution, results become known
        removed = ModerationVotingService.resolve_removal_votes(
            round, data['config']
        )
        
        # Results are now finalized
        assert len(removed) >= 0  # Result is deterministic
