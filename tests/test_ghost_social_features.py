"""
Tests for Ghost Social Features: Quoting, Notification Preferences, and Join Request Messages
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import (
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    NotificationPreference,
    JoinRequest,
    PlatformConfig
)
from core.services.quote_service import QuoteService
from core.services.notification_service import NotificationService

User = get_user_model()


@pytest.mark.django_db
class TestResponseQuoting:
    """Test quote selector component and API integration."""
    
    def setup_method(self):
        """Set up test data."""
        self.client = Client()
        
        # Ensure PlatformConfig exists
        config = PlatformConfig.load()
        
        # Create users
        self.user1 = User.objects.create_user(
            username="quoter",
            phone_number="+15551234567",
            password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="original",
            phone_number="+15559876543",
            password="testpass123"
        )
        
        # Create discussion and participants
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Testing quoting feature",
            initiator=self.user1,
            status="active",
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes
        )
        
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=self.user1,
            role="initiator"
        )
        
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=self.user2,
            role="active"
        )
        
        # Create round
        self.round = Round.objects.create(
            discussion=self.discussion,
            round_number=1,
            status="active"
        )
        
        # Create response to quote
        self.original_response = Response.objects.create(
            round=self.round,
            user=self.user2,
            content="This is the original response that will be quoted.",
            character_count=50
        )
    
    def test_quote_service_creates_quote_metadata(self):
        """Test that QuoteService creates proper quote metadata."""
        quote_data = QuoteService.create_quote(
            source_response=self.original_response,
            quoted_text="original response"
        )
        
        assert quote_data["author"] == "original"
        assert "original response" in quote_data["quoted_text"]
        assert quote_data["response_id"] == str(self.original_response.id)
        assert quote_data["round_number"] == 1
    
    def test_quote_service_validates_text_exists(self):
        """Test that QuoteService validates quoted text exists in response."""
        from django.core.exceptions import ValidationError
        
        with pytest.raises(ValidationError):
            QuoteService.create_quote(
                source_response=self.original_response,
                quoted_text="This text does not exist in the response"
            )
    
    def test_quote_api_endpoint(self):
        """Test POST /api/responses/{id}/quote/ endpoint."""
        self.client.login(username="quoter", password="testpass123")
        
        url = reverse('core:create-quote', kwargs={'response_id': self.original_response.id})
        
        response = self.client.post(
            url,
            data={'quoted_text': 'original response'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.json()
        assert 'quote_markdown' in data
        assert 'original' in data['quote_markdown']
    
    def test_quote_selector_component_renders(self):
        """Test that quote_selector.html component renders with responses."""
        self.client.login(username="quoter", password="testpass123")
        
        url = reverse('discussion-participate', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        # Check that quote selector script is present
        assert b'quote-selector' in response.content
        assert b'showQuotePreview' in response.content
    
    def test_response_card_has_data_attributes(self):
        """Test that response_card.html has data attributes for quoting."""
        self.client.login(username="quoter", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        # Check for data attributes
        assert b'data-response-id' in response.content
        assert b'data-author' in response.content
        assert b'data-number' in response.content


@pytest.mark.django_db
class TestNotificationPreferences:
    """Test notification preferences center."""
    
    def setup_method(self):
        """Set up test data."""
        self.client = Client()
        
        self.user = User.objects.create_user(
            username="testuser",
            phone_number="+15551234567",
            password="testpass123"
        )
        
        # Create default preferences
        NotificationService.create_notification_preferences(self.user)
    
    def test_notification_preferences_page_loads(self):
        """Test that notification preferences page loads."""
        self.client.login(username="testuser", password="testpass123")
        
        # Use the view URL (not API)
        url = '/notifications/preferences/'
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert b'Notification Preferences' in response.content
        assert b'Discussion Activity' in response.content
    
    def test_notification_preferences_displays_all_types(self):
        """Test that all notification types are displayed."""
        self.client.login(username="testuser", password="testpass123")
        
        url = '/notifications/preferences/'
        response = self.client.get(url)
        
        # Check for actual notification types that exist in the system
        assert b'new_response_posted' in response.content or b'New Response Posted' in response.content
        assert b'voting' in response.content or b'Voting' in response.content
    
    def test_notification_preferences_shows_delivery_toggles(self):
        """Test that delivery method toggles are shown."""
        self.client.login(username="testuser", password="testpass123")
        
        url = '/notifications/preferences/'
        response = self.client.get(url)
        
        # Check for delivery method checkboxes
        assert b'in_app' in response.content
        assert b'email' in response.content
        assert b'push' in response.content
    
    def test_update_notification_preferences_via_form(self):
        """Test updating preferences via POST."""
        self.client.login(username="testuser", password="testpass123")
        
        url = '/notifications/preferences/'
        
        # Update preferences
        response = self.client.post(url, {
            'pref_new_response_posted_email': 'on',
            'pref_new_response_posted_in_app': 'on',
            'pref_voting_window_opened_push': 'on',
        })
        
        assert response.status_code == 302  # Redirect after success
        
        # Verify preferences were updated
        pref = NotificationPreference.objects.get(
            user=self.user,
            notification_type='new_response_posted'
        )
        
        assert pref.delivery_method.get('email') is True
        assert pref.delivery_method.get('in_app') is True
    
    def test_api_get_notification_preferences(self):
        """Test GET /api/notifications/preferences/ endpoint."""
        self.client.login(username="testuser", password="testpass123")
        
        url = reverse('core:notification-preferences')
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert 'preferences' in data
        assert len(data['preferences']) > 0
    
    def test_api_update_notification_preferences(self):
        """Test PATCH /api/notifications/preferences/ endpoint."""
        self.client.login(username="testuser", password="testpass123")
        
        url = reverse('core:update-notification-preferences')
        
        response = self.client.patch(
            url,
            data={
                'preferences': [
                    {
                        'type': 'new_response_posted',
                        'enabled': True,
                        'delivery_methods': {
                            'in_app': True,
                            'email': True,
                            'push': False
                        }
                    }
                ]
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # Verify update
        pref = NotificationPreference.objects.get(
            user=self.user,
            notification_type='new_response_posted'
        )
        
        assert pref.enabled is True
        assert pref.delivery_method['email'] is True


@pytest.mark.django_db
class TestJoinRequestMessages:
    """Test join request message display in moderator dashboard."""
    
    def setup_method(self):
        """Set up test data."""
        self.client = Client()
        
        # Ensure PlatformConfig exists
        config = PlatformConfig.load()
        
        # Create users
        self.initiator = User.objects.create_user(
            username="initiator",
            phone_number="+15551234567",
            password="testpass123"
        )
        
        self.requester = User.objects.create_user(
            username="requester",
            phone_number="+15559876543",
            password="testpass123"
        )
        
        # Create discussion
        self.discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Testing join requests",
            initiator=self.initiator,
            status="active",
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes
        )
        
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=self.initiator,
            role="initiator"
        )
        
        # Create join request with message
        self.join_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=self.requester,
            approver=self.initiator,
            status="pending",
            request_message="I would love to join this discussion because I have relevant experience."
        )
    
    def test_join_requests_visible_to_initiator(self):
        """Test that join requests are visible to discussion initiator."""
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert b'Pending Join Requests' in response.content
        assert b'requester' in response.content
    
    def test_request_message_displayed(self):
        """Test that request message is displayed in the UI."""
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert b'Request Message:' in response.content
        assert b'relevant experience' in response.content
    
    def test_no_message_shows_placeholder(self):
        """Test that placeholder shown when no request message."""
        # Create request without message
        no_msg_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=User.objects.create_user(
                username="nomsg",
                phone_number="+15555555555",
                password="test"
            ),
            approver=self.initiator,
            status="pending",
            request_message=""
        )
        
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert b'No message provided' in response.content
    
    def test_response_message_in_history(self):
        """Test that response messages appear in request history."""
        # Create resolved request with response message
        resolved_request = JoinRequest.objects.create(
            discussion=self.discussion,
            requester=User.objects.create_user(
                username="declined",
                phone_number="+15554444444",
                password="test"
            ),
            approver=self.initiator,
            status="declined",
            request_message="Please let me join",
            response_message="Sorry, the discussion is full."
        )
        resolved_request.resolved_at = resolved_request.created_at
        resolved_request.save()
        
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        # History is in a details element
        assert b'Recent Request History' in response.content or b'Request History' in response.content
    
    def test_approve_join_request_api(self):
        """Test approving join request via API."""
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('core:approve-join-request', kwargs={'request_id': self.join_request.id})
        
        response = self.client.post(url)
        
        assert response.status_code == 200
        
        # Verify request was approved
        self.join_request.refresh_from_db()
        assert self.join_request.status == 'approved'
        
        # Verify participant was created
        assert DiscussionParticipant.objects.filter(
            discussion=self.discussion,
            user=self.requester
        ).exists()
    
    def test_decline_join_request_with_message(self):
        """Test declining join request with response message."""
        self.client.login(username="initiator", password="testpass123")
        
        url = reverse('core:decline-join-request', kwargs={'request_id': self.join_request.id})
        
        response = self.client.post(
            url,
            data={'response_message': 'The discussion has reached capacity.'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # Verify request was declined with message
        self.join_request.refresh_from_db()
        assert self.join_request.status == 'declined'
        assert self.join_request.response_message == 'The discussion has reached capacity.'
    
    def test_join_requests_not_visible_to_regular_participants(self):
        """Test that join requests are not visible to regular participants."""
        regular_user = User.objects.create_user(
            username="regular",
            phone_number="+15556666666",
            password="testpass123"
        )
        
        DiscussionParticipant.objects.create(
            discussion=self.discussion,
            user=regular_user,
            role="active"
        )
        
        self.client.login(username="regular", password="testpass123")
        
        url = reverse('discussion-detail', kwargs={'discussion_id': self.discussion.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        # Should not see join requests section
        assert b'Pending Join Requests' not in response.content or response.content.count(b'Pending Join Requests') == 0


class TestQuoteServiceUnit(TestCase):
    """Unit tests for QuoteService methods."""
    
    def setUp(self):
        """Set up test data."""
        config = PlatformConfig.load()
        
        self.user = User.objects.create_user(
            username="testuser",
            phone_number="+15551234567"
        )
        
        self.discussion = Discussion.objects.create(
            topic_headline="Test",
            topic_details="Test",
            initiator=self.user,
            max_response_length_chars=config.mrl_max_chars,
            response_time_multiplier=1.0,
            min_response_time_minutes=config.mrm_min_minutes
        )
        
        self.round = Round.objects.create(
            discussion=self.discussion,
            round_number=1
        )
        
        self.response = Response.objects.create(
            round=self.round,
            user=self.user,
            content="This is a test response with important information.",
            character_count=50
        )
    
    def test_format_quote_for_display(self):
        """Test quote markdown formatting."""
        quote_data = QuoteService.create_quote(
            source_response=self.response,
            quoted_text="important information"
        )
        
        formatted = QuoteService.format_quote_for_display(quote_data)
        
        assert ">" in formatted  # Markdown blockquote
        assert "testuser" in formatted
        assert "important information" in formatted
    
    def test_create_quote_markdown(self):
        """Test create_quote_markdown method."""
        markdown = QuoteService.create_quote_markdown(
            source_response=self.response,
            quoted_text="important information"
        )
        
        assert ">" in markdown
        assert "important information" in markdown
