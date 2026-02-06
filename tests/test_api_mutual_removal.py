"""
Tests for deprecated mutual removal API endpoints.

All mutual removal endpoints should return 410 Gone as the feature
has been deprecated.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    UserFactory,
    DiscussionFactory,
    RoundFactory,
)


@pytest.mark.django_db
class TestMutualRemovalDeprecation:
    """Test mutual removal endpoints return 410 Gone"""

    def setup_method(self):
        """Set up test client and common test data"""
        self.client = APIClient()

    def test_initiate_mutual_removal_returns_410(self):
        """Test initiate endpoint returns 410 Gone"""
        # Create discussion
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='in_progress')

        # Create user
        user = UserFactory()
        self.client.force_authenticate(user=user)

        # Make API request
        url = reverse('core:initiate-mutual-removal', kwargs={
            'discussion_id': discussion.id
        })
        response = self.client.post(url, {}, format='json')

        # Verify 410 Gone response
        assert response.status_code == status.HTTP_410_GONE
        assert 'error' in response.data
        assert response.data['error'] == 'Feature deprecated'
        assert 'deprecated_date' in response.data
        assert response.data['deprecated_date'] == '2026-02'

    def test_respond_mutual_removal_returns_410(self):
        """Test respond endpoint returns 410 Gone"""
        # Create discussion
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='in_progress')

        # Create user
        user = UserFactory()
        self.client.force_authenticate(user=user)

        # Make API request with fake attack_id
        url = reverse('core:respond-mutual-removal', kwargs={
            'discussion_id': discussion.id,
            'attack_id': 1
        })
        response = self.client.post(url, {}, format='json')

        # Verify 410 Gone response
        assert response.status_code == status.HTTP_410_GONE
        assert 'error' in response.data
        assert response.data['error'] == 'Feature deprecated'
        assert 'deprecated_date' in response.data
        assert response.data['deprecated_date'] == '2026-02'

    def test_check_status_returns_410(self):
        """Test status endpoint returns 410 Gone"""
        # Create discussion
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='in_progress')

        # Create user
        user = UserFactory()
        self.client.force_authenticate(user=user)

        # Make API request
        url = reverse('core:check-mutual-removal-status', kwargs={
            'discussion_id': discussion.id
        })
        response = self.client.get(url)

        # Verify 410 Gone response
        assert response.status_code == status.HTTP_410_GONE
        assert 'error' in response.data
        assert response.data['error'] == 'Feature deprecated'
        assert 'deprecated_date' in response.data
        assert response.data['deprecated_date'] == '2026-02'
        # Legacy clients might check this field
        assert 'status' in response.data
        assert response.data['status'] == 'no_active_attacks'

    def test_mutual_removal_deprecation_message(self):
        """Test deprecation message includes helpful information"""
        # Create discussion
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status='in_progress')

        # Create user
        user = UserFactory()
        self.client.force_authenticate(user=user)

        # Make API request to initiate endpoint
        url = reverse('core:initiate-mutual-removal', kwargs={
            'discussion_id': discussion.id
        })
        response = self.client.post(url, {}, format='json')

        # Verify detailed deprecation message
        assert response.status_code == status.HTTP_410_GONE
        assert 'message' in response.data
        assert 'deprecated' in response.data['message'].lower()
        assert 'removed from the platform' in response.data['message']

        # Verify alternative suggested
        assert 'alternative' in response.data
        assert 'removal voting system' in response.data['alternative']
        assert 'voting phases' in response.data['alternative']

    def test_initiate_requires_authentication(self):
        """Test initiate endpoint requires authentication"""
        # Create discussion
        discussion = DiscussionFactory()

        # Make API request without authentication
        url = reverse('core:initiate-mutual-removal', kwargs={
            'discussion_id': discussion.id
        })
        response = self.client.post(url, {}, format='json')

        # Verify authentication required (401 or 403)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_respond_requires_authentication(self):
        """Test respond endpoint requires authentication"""
        # Create discussion
        discussion = DiscussionFactory()

        # Make API request without authentication
        url = reverse('core:respond-mutual-removal', kwargs={
            'discussion_id': discussion.id,
            'attack_id': 1
        })
        response = self.client.post(url, {}, format='json')

        # Verify authentication required (401 or 403)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_status_requires_authentication(self):
        """Test status endpoint requires authentication"""
        # Create discussion
        discussion = DiscussionFactory()

        # Make API request without authentication
        url = reverse('core:check-mutual-removal-status', kwargs={
            'discussion_id': discussion.id
        })
        response = self.client.get(url)

        # Verify authentication required (401 or 403)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
