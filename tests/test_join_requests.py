"""
Tests for join request system.

Tests request creation, approval, decline, and permissions.
"""

import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from core.models import JoinRequest, DiscussionParticipant, PlatformConfig
from core.services.join_request import JoinRequestService


@pytest.mark.django_db
class TestJoinRequestService:
    """Test join request service."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)
    
    def test_create_join_request(self, user_factory, discussion_factory):
        """Test creating join request."""
        requester = user_factory()
        discussion = discussion_factory()
        initiator = user_factory()
        
        # Add initiator as participant
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=initiator,
            role='active'
        )
        
        with patch('core.tasks.send_join_request_notification.delay'):
            request = JoinRequestService.create_request(
                discussion,
                requester,
                "I'd like to join this discussion"
            )
        
        assert request.requester == requester
        assert request.discussion == discussion
        assert request.status == 'pending'
        assert request.approver == initiator
    
    def test_create_request_already_participant(self, user_factory, discussion_factory):
        """Test cannot create request if already participant."""
        requester = user_factory()
        discussion = discussion_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=requester,
            role='active'
        )
        
        with pytest.raises(ValidationError) as exc_info:
            JoinRequestService.create_request(discussion, requester)
        
        assert 'already a participant' in str(exc_info.value).lower()
    
    def test_create_request_discussion_at_cap(self, user_factory, discussion_factory):
        """Test cannot create request if discussion at capacity."""
        config = PlatformConfig.objects.get(pk=1)
        discussion = discussion_factory()
        
        # Fill discussion to capacity
        for _ in range(config.max_discussion_participants):
            user = user_factory()
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=user,
                role='active'
            )
        
        requester = user_factory()
        
        with pytest.raises(ValidationError) as exc_info:
            JoinRequestService.create_request(discussion, requester)
        
        assert 'maximum capacity' in str(exc_info.value).lower()
    
    def test_create_request_duplicate(self, user_factory, discussion_factory):
        """Test cannot create duplicate pending request."""
        requester = user_factory()
        discussion = discussion_factory()
        initiator = user_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=initiator,
            role='active'
        )
        
        with patch('core.tasks.send_join_request_notification.delay'):
            JoinRequestService.create_request(discussion, requester)
        
        with pytest.raises(ValidationError) as exc_info:
            JoinRequestService.create_request(discussion, requester)
        
        assert 'pending request' in str(exc_info.value).lower()
    
    def test_approve_request(self, user_factory, discussion_factory):
        """Test approving join request."""
        requester = user_factory()
        approver = user_factory()
        discussion = discussion_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=approver,
            role='active'
        )
        
        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=approver,
            status='pending'
        )
        
        with patch('core.tasks.send_join_request_approved_notification.delay'):
            participant = JoinRequestService.approve_request(request, approver)
        
        assert participant.user == requester
        assert participant.discussion == discussion
        assert participant.role == 'active'
        
        request.refresh_from_db()
        assert request.status == 'approved'
        assert request.resolved_at is not None
    
    def test_approve_request_not_approver(self, user_factory, discussion_factory):
        """Test cannot approve if not designated approver."""
        requester = user_factory()
        approver = user_factory()
        other_user = user_factory()
        discussion = discussion_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=approver,
            role='active'
        )
        
        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=approver,
            status='pending'
        )
        
        with pytest.raises(ValidationError) as exc_info:
            JoinRequestService.approve_request(request, other_user)
        
        assert 'permission' in str(exc_info.value).lower()
    
    def test_decline_request(self, user_factory, discussion_factory):
        """Test declining join request."""
        requester = user_factory()
        approver = user_factory()
        discussion = discussion_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=approver,
            role='active'
        )
        
        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=approver,
            status='pending'
        )
        
        with patch('core.tasks.send_join_request_declined_notification.delay'):
            JoinRequestService.decline_request(
                request,
                approver,
                "Thanks but we're full"
            )
        
        request.refresh_from_db()
        assert request.status == 'declined'
        assert request.response_message == "Thanks but we're full"
        assert request.resolved_at is not None


@pytest.mark.django_db
class TestJoinRequestAPI:
    """Test join request API endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        PlatformConfig.objects.get_or_create(pk=1)
    
    def test_create_join_request_endpoint(
        self, authenticated_client, user_factory, discussion_factory
    ):
        """Test creating join request via API."""
        discussion = discussion_factory()
        initiator = user_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=initiator,
            role='active'
        )
        
        with patch('core.tasks.send_join_request_notification.delay'):
            response = authenticated_client.post(
                f'/api/discussions/{discussion.id}/join-request/',
                {'message': 'Please let me join'}
            )
        
        assert response.status_code == 201
        assert 'id' in response.data
        assert response.data['status'] == 'pending'
    
    def test_get_join_requests(
        self, authenticated_client, user_factory, discussion_factory
    ):
        """Test getting join requests for discussion."""
        discussion = discussion_factory()
        
        # Make authenticated user a participant
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=authenticated_client.user,
            role='active'
        )
        
        # Create some requests
        requester = user_factory()
        JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=authenticated_client.user,
            status='pending'
        )
        
        response = authenticated_client.get(
            f'/api/discussions/{discussion.id}/join-requests/'
        )
        
        assert response.status_code == 200
        assert len(response.data['pending']) == 1
    
    def test_approve_join_request_endpoint(
        self, authenticated_client, user_factory, discussion_factory
    ):
        """Test approving join request via API."""
        discussion = discussion_factory()
        requester = user_factory()
        
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=authenticated_client.user,
            role='active'
        )
        
        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=authenticated_client.user,
            status='pending'
        )
        
        with patch('core.tasks.send_join_request_approved_notification.delay'):
            response = authenticated_client.post(
                f'/api/join-requests/{request.id}/approve/'
            )
        
        assert response.status_code == 200
        assert 'participant_id' in response.data
        
        # Check requester is now participant
        assert DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester
        ).exists()
