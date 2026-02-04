"""Tests for email service and templates."""

import pytest
from django.core import mail
from django.test import override_settings

from core.services.email_service import EmailService
from tests.factories import UserFactory


@pytest.mark.django_db
class TestEmailService:
    """Test email service functionality."""

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_discussion_invite_email(self):
        """Test sending discussion invite email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_discussion_invite(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            initiator_name='John Doe',
            participant_count=5,
            action_url='http://example.com/discussion/1'
        )
        
        assert result is True
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert 'Test Discussion' in mail.outbox[0].subject

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_mrp_expiring_email(self):
        """Test sending MRP expiring email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_mrp_expiring_email(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            hours_remaining=24,
            action_url='http://example.com/discussion/1'
        )
        
        assert result is True
        assert len(mail.outbox) == 1
        assert '24' in mail.outbox[0].body or '24' in str(mail.outbox[0].alternatives[0][0])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_voting_started_email(self):
        """Test sending voting started email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_voting_started_email(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            vote_question='Should we continue?',
            voting_deadline='2024-12-31',
            action_url='http://example.com/vote/1'
        )
        
        assert result is True
        assert len(mail.outbox) == 1

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_moved_to_observer_email(self):
        """Test sending moved to observer email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_moved_to_observer_email(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            reason='voted_out',
            can_rejoin=True,
            wait_period='2 rounds',
            action_url='http://example.com/discussion/1'
        )
        
        assert result is True
        assert len(mail.outbox) == 1

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_has_html_and_text_versions(self):
        """Test that emails include both HTML and plain text."""
        user = UserFactory(email='test@example.com')
        
        EmailService.send_discussion_invite(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            initiator_name='John Doe',
            participant_count=5,
            action_url='http://example.com/discussion/1'
        )
        
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        
        # Should have both plain text body
        assert email.body
        
        # And HTML alternative
        assert len(email.alternatives) > 0
        html_content, mime_type = email.alternatives[0]
        assert mime_type == 'text/html'
        assert '<html' in html_content.lower()

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_new_response_email(self):
        """Test sending new response email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_new_response_email(
            recipient_email=user.email,
            recipient_name=user.username,
            topic='Test Discussion',
            author_name='Jane Smith',
            round_number=2,
            action_url='http://example.com/response/1'
        )
        
        assert result is True
        assert len(mail.outbox) == 1

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_escalation_warning_email(self):
        """Test sending escalation warning email."""
        user = UserFactory(email='test@example.com')
        
        result = EmailService.send_escalation_warning_email(
            recipient_email=user.email,
            recipient_name=user.username,
            count=3
        )
        
        assert result is True
        assert len(mail.outbox) == 1
