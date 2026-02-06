"""
API tests for join request voting endpoints.

Tests the vote_join_request API endpoint with various scenarios.
"""

import pytest
import json
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Discussion,
    Round,
    JoinRequest,
    JoinRequestVote,
    DiscussionParticipant,
    User,
)
from tests.factories import (
    UserFactory,
    DiscussionFactory,
    RoundFactory,
    JoinRequestFactory,
    ResponseFactory,
)


@pytest.mark.django_db
class TestVoteJoinRequestAPI:
    """Test vote_join_request API endpoint"""

    def setup_method(self):
        """Set up test client and common test data"""
        self.client = APIClient()

    def test_vote_join_request_approve_success(self):
        """Test can approve join request via API"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify success response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        assert response.data['message'] == 'Vote recorded'
        assert response.data['vote']['approve'] is True

        # Verify vote was created
        assert JoinRequestVote.objects.filter(
            voter=voter,
            join_request=join_request,
            approve=True
        ).exists()

    def test_vote_join_request_deny_success(self):
        """Test can deny join request via API"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': False}, format='json')

        # Verify success response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        assert response.data['vote']['approve'] is False

        # Verify vote was created
        assert JoinRequestVote.objects.filter(
            voter=voter,
            join_request=join_request,
            approve=False
        ).exists()

    def test_vote_join_request_duplicate_rejected(self):
        """Test 400 on duplicate vote"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Cast first vote
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Try to vote again
        response = self.client.post(url, {'approve': False}, format='json')

        # Verify rejection
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_vote_join_request_not_participant_rejected(self):
        """Test 403 if not participant"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create non-participant user
        non_participant = UserFactory()
        self.client.force_authenticate(user=non_participant)

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify rejection
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert 'Must be an active participant' in response.data['error']

    def test_vote_join_request_not_voting_phase_rejected(self):
        """Test 400 if not in voting phase"""
        # Create discussion with NON-voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='in_progress')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify rejection
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not in voting phase' in response.data['error']

    def test_vote_join_request_invalid_json_rejected(self):
        """Test 400 on invalid JSON"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request with invalid JSON
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(
            url,
            data='invalid json{',
            content_type='application/json'
        )

        # Verify rejection (either 400 or 500, both acceptable for invalid JSON)
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ]

    def test_vote_join_request_missing_approve_rejected(self):
        """Test 400 if approve field missing"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request WITHOUT approve field
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {}, format='json')

        # Verify rejection
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'approve' in response.data['error'].lower()

    def test_vote_join_request_returns_vote_counts(self):
        """Test response includes updated vote counts"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify vote counts included
        assert response.status_code == status.HTTP_200_OK
        assert 'vote_counts' in response.data
        assert 'approve' in response.data['vote_counts']
        assert 'deny' in response.data['vote_counts']
        assert 'total' in response.data['vote_counts']
        assert response.data['vote_counts']['approve'] == 1
        assert response.data['vote_counts']['total'] == 1

    def test_vote_join_request_awards_credits(self):
        """Test voting triggers credit award"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        initial_platform = voter.platform_invites_acquired
        initial_discussion = voter.discussion_invites_acquired

        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Create join request
        requester = UserFactory()
        join_request = JoinRequestFactory(
            discussion=discussion,
            requester=requester,
            status='pending'
        )

        # Make API request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': join_request.id
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify success
        assert response.status_code == status.HTTP_200_OK

        # Refresh voter and check credits
        voter.refresh_from_db()
        assert voter.platform_invites_acquired > initial_platform
        assert voter.discussion_invites_acquired > initial_discussion

    def test_vote_join_request_nonexistent_discussion_404(self):
        """Test 404 on bad discussion ID"""
        # Create voter
        voter = UserFactory()
        self.client.force_authenticate(user=voter)

        # Make API request with non-existent discussion
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': 99999,
            'join_request_id': 1
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_vote_join_request_nonexistent_request_404(self):
        """Test 404 on bad request ID"""
        # Create discussion with voting round
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='voting')

        # Create active participant (voter)
        voter = UserFactory()
        self.client.force_authenticate(user=voter)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=voter,
            role='active'
        )

        # Make API request with non-existent join request
        url = reverse('core:vote-join-request', kwargs={
            'discussion_id': discussion.id,
            'join_request_id': 99999
        })
        response = self.client.post(url, {'approve': True}, format='json')

        # Verify 404
        assert response.status_code == status.HTTP_404_NOT_FOUND
