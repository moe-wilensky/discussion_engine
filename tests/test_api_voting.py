"""
Tests for voting API endpoints.

Tests full voting flow via API.
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from core.models import (
    User, Discussion, Round, DiscussionParticipant,
    PlatformConfig, Response
)


@pytest.mark.django_db
class TestVotingAPI:
    """Test voting API endpoints"""

    @pytest.fixture
    def setup_api_scenario(self):
        """Setup for API testing"""
        config = PlatformConfig.load()
        
        # Create users
        users = []
        for i in range(4):
            user = User.objects.create_user(
                username=f'user{i}',
                phone_number=f'+1123456789{i}',
                password='test123'
            )
            users.append(user)
        
        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline='API Test',
            topic_details='Testing voting API',
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
        
        # Create round in voting status
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='voting',
            final_mrp_minutes=60.0,
            end_time=timezone.now() - timedelta(minutes=10)
        )
        
        # Add responses
        for user in users[:3]:  # 3 users responded
            Response.objects.create(
                round=round, user=user,
                content='Response', character_count=8
            )
        
        return {
            'config': config,
            'users': users,
            'discussion': discussion,
            'round': round
        }

    def test_voting_status_endpoint(self, setup_api_scenario):
        """Test GET /voting/status/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.get(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/status/'
        )
        
        assert response.status_code == 200
        assert response.data['voting_window_open'] is True
        assert response.data['user_is_eligible'] is True
        assert response.data['eligible_voters_count'] == 3

    def test_cast_parameter_vote_endpoint(self, setup_api_scenario):
        """Test POST /voting/parameters/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/parameters/',
            {
                'mrl_vote': 'increase',
                'rtm_vote': 'no_change'
            },
            format='json'
        )
        
        assert response.status_code == 200
        assert response.data['vote_recorded'] is True
        assert 'current_results' in response.data

    def test_parameter_results_endpoint(self, setup_api_scenario):
        """Test GET /voting/parameter-results/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        
        # Cast some votes first
        from core.services.voting_service import VotingService
        VotingService.cast_parameter_vote(
            user, round, 'increase', 'decrease'
        )
        VotingService.cast_parameter_vote(
            data['users'][1], round, 'increase', 'no_change'
        )
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.get(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/parameter-results/'
        )
        
        assert response.status_code == 200
        assert 'mrl' in response.data
        assert 'rtm' in response.data
        assert response.data['mrl']['increase'] == 2

    def test_removal_targets_endpoint(self, setup_api_scenario):
        """Test GET /voting/removal-targets/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.get(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/removal-targets/'
        )
        
        assert response.status_code == 200
        assert 'eligible_targets' in response.data
        # User shouldn't see themselves as target
        target_ids = [t['user_id'] for t in response.data['eligible_targets']]
        assert str(user.id) not in target_ids

    def test_cast_removal_vote_endpoint(self, setup_api_scenario):
        """Test POST /voting/removal/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        target = data['users'][1]
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/removal/',
            {
                'target_user_ids': [str(target.id)]
            },
            format='json'
        )
        
        assert response.status_code == 200
        assert response.data['votes_cast'] == 1

    def test_removal_results_endpoint(self, setup_api_scenario):
        """Test GET /voting/removal-results/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        target = data['users'][1]
        
        # Cast removal votes
        from core.services.moderation_voting_service import ModerationVotingService
        ModerationVotingService.cast_removal_vote(
            user, round, [target]
        )
        ModerationVotingService.cast_removal_vote(
            data['users'][2], round, [target]
        )
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.get(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/removal-results/'
        )
        
        assert response.status_code == 200
        assert 'targets' in response.data
        assert len(response.data['targets']) > 0

    def test_observer_status_endpoint(self, setup_api_scenario):
        """Test GET /observer-status/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        user = data['users'][1]
        
        # Make user an observer
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=user
        )
        participant.role = 'temporary_observer'
        participant.observer_reason = 'mutual_removal'
        participant.observer_since = timezone.now() - timedelta(hours=1)
        participant.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.get(
            f'/api/discussions/{discussion.id}/observer-status/'
        )
        
        assert response.status_code == 200
        assert response.data['user_role'] == 'temporary_observer'
        assert response.data['observer_reason'] == 'mutual_removal'

    def test_rejoin_discussion_endpoint(self, setup_api_scenario):
        """Test POST /rejoin/ endpoint"""
        data = setup_api_scenario
        discussion = data['discussion']
        user = data['users'][1]
        
        # Create current round
        Round.objects.create(
            discussion=discussion,
            round_number=2,
            status='in_progress',
            final_mrp_minutes=60.0
        )
        
        # Make user an observer who can rejoin
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=user
        )
        participant.role = 'temporary_observer'
        participant.observer_reason = 'mutual_removal'
        participant.observer_since = timezone.now() - timedelta(hours=2)
        participant.posted_in_round_when_removed = False
        participant.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            f'/api/discussions/{discussion.id}/rejoin/',
            format='json'
        )
        
        assert response.status_code == 200
        assert response.data['rejoined'] is True
        assert response.data['new_role'] == 'active'

    def test_voting_not_open_error(self, setup_api_scenario):
        """Test error when voting window not open"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        user = data['users'][0]
        
        # Close voting
        round.status = 'completed'
        round.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/parameters/',
            {
                'mrl_vote': 'increase',
                'rtm_vote': 'no_change'
            },
            format='json'
        )
        
        assert response.status_code == 400
        assert 'not open' in str(response.data['error']).lower()

    def test_full_voting_flow_via_api(self, setup_api_scenario):
        """Test complete voting flow through API"""
        data = setup_api_scenario
        discussion = data['discussion']
        round = data['round']
        
        client = APIClient()
        
        # All eligible users vote
        for i, user in enumerate(data['users'][:3]):
            client.force_authenticate(user=user)
            
            # Parameter vote
            response = client.post(
                f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/parameters/',
                {
                    'mrl_vote': 'increase' if i < 2 else 'decrease',
                    'rtm_vote': 'no_change'
                },
                format='json'
            )
            assert response.status_code == 200
            
            # Removal vote (vote for next user if not last)
            if i < 2:
                target = data['users'][i + 1]
                response = client.post(
                    f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/removal/',
                    {
                        'target_user_ids': [str(target.id)]
                    },
                    format='json'
                )
                assert response.status_code == 200
        
        # Check final results
        client.force_authenticate(user=data['users'][0])
        response = client.get(
            f'/api/discussions/{discussion.id}/rounds/{round.round_number}/voting/parameter-results/'
        )
        
        assert response.status_code == 200
        # 2 increase, 1 decrease for MRL
        assert response.data['mrl']['increase'] == 2
        assert response.data['mrl']['decrease'] == 1
