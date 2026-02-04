"""Tests for email service and templates."""

import pytest
from django.core import mail
from django.core.cache import cache
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

    def test_validate_email_with_valid_addresses(self):
        """Test email validation with valid addresses."""
        assert EmailService.validate_email('user@example.com') is True
        assert EmailService.validate_email('test.user+tag@domain.co.uk') is True
        assert EmailService.validate_email('name@subdomain.domain.com') is True

    def test_validate_email_with_invalid_addresses(self):
        """Test email validation with invalid addresses."""
        assert EmailService.validate_email('not-an-email') is False
        assert EmailService.validate_email('missing@domain') is False
        assert EmailService.validate_email('@nodomain.com') is False
        assert EmailService.validate_email('spaces in@email.com') is False
        assert EmailService.validate_email('') is False

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_email_rejects_invalid_address(self):
        """Test that send_email rejects invalid email addresses."""
        result = EmailService.send_email(
            recipient_email='invalid-email',
            subject='Test',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        assert result is False
        assert len(mail.outbox) == 0

    def test_email_rate_limit_allows_within_limit(self):
        """Test that emails within rate limit are allowed."""
        cache.clear()
        email = 'ratetest1@example.com'

        # First 10 emails should pass (default limit)
        for i in range(10):
            assert EmailService.check_rate_limit(email) is True

    def test_email_rate_limit_blocks_after_limit(self):
        """Test that emails are blocked after exceeding rate limit."""
        cache.clear()
        email = 'ratetest2@example.com'

        # Send 10 emails (the limit)
        for i in range(10):
            EmailService.check_rate_limit(email)

        # 11th email should be blocked
        assert EmailService.check_rate_limit(email) is False

    def test_email_rate_limit_is_per_recipient(self):
        """Test that rate limiting is per recipient."""
        cache.clear()
        email1 = 'ratetest3@example.com'
        email2 = 'ratetest4@example.com'

        # Send 10 emails to email1
        for i in range(10):
            EmailService.check_rate_limit(email1)

        # email1 should be blocked
        assert EmailService.check_rate_limit(email1) is False

        # But email2 should still work
        assert EmailService.check_rate_limit(email2) is True

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_RATE_LIMIT=3
    )
    def test_send_email_respects_rate_limit(self):
        """Test that send_email respects rate limiting."""
        cache.clear()
        email = 'ratetest5@example.com'

        # Send 3 valid emails (custom limit of 3)
        for i in range(3):
            result = EmailService.send_email(
                recipient_email=email,
                subject=f'Test {i}',
                template_name='discussion_invite',
                context={'recipient_name': 'Test'},
            )

        # 4th email should fail due to rate limiting
        result = EmailService.send_email(
            recipient_email=email,
            subject='Test 4',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        assert result is False

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_validation_before_rate_limiting(self):
        """Test that email validation happens before rate limiting check."""
        cache.clear()

        # Try to send many emails with invalid address
        for i in range(12):
            result = EmailService.send_email(
                recipient_email='invalid-email',
                subject='Test',
                template_name='discussion_invite',
                context={'recipient_name': 'Test'},
            )
            assert result is False

        # All should fail due to validation, not rate limiting
        # So a valid email should still work
        assert EmailService.check_rate_limit('valid@example.com') is True
