"""
Tests for data protection features.

Tests phone number masking, email validation, and rate limiting.
"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from core.services.email_service import EmailService

User = get_user_model()


@pytest.mark.django_db
class TestPhoneNumberMasking(TestCase):
    """Test phone number masking in API responses."""

    def setUp(self):
        """Set up test users and client."""
        self.client = APIClient()

        # Create test users
        self.user1 = User.objects.create_user(
            username="user1",
            phone_number="+12345678901",
        )
        self.user2 = User.objects.create_user(
            username="user2",
            phone_number="+19876543210",
        )
        self.admin = User.objects.create_user(
            username="admin",
            phone_number="+11111111111",
            is_staff=True,
        )

    def test_user_sees_own_full_phone_number(self):
        """Test that users can see their own full phone number."""
        # Test using the UserSerializer directly with context
        from core.api.serializers import UserSerializer

        # Create a mock request with the user
        self.client.force_authenticate(user=self.user1)
        request = self.client.get('/').wsgi_request
        request.user = self.user1

        # Serialize user1 with user1's request context
        serializer = UserSerializer(self.user1, context={'request': request})

        # User should see their own full phone number
        self.assertEqual(serializer.data['phone_number'], '+12345678901')

    def test_user_sees_masked_phone_number_for_others(self):
        """Test that users see masked phone numbers for other users."""
        from core.api.serializers import UserSerializer

        # Create a mock request with user1
        self.client.force_authenticate(user=self.user1)
        request = self.client.get('/').wsgi_request
        request.user = self.user1

        # Serialize user2 with user1's request context
        serializer = UserSerializer(self.user2, context={'request': request})

        # Should show only last 4 digits
        self.assertEqual(serializer.data['phone_number'], '***-***-3210')

    def test_admin_sees_full_phone_numbers(self):
        """Test that admins can see all phone numbers."""
        from core.api.serializers import UserSerializer

        # Create a mock request with admin
        self.client.force_authenticate(user=self.admin)
        request = self.client.get('/').wsgi_request
        request.user = self.admin

        # Serialize user1 with admin's request context
        serializer = UserSerializer(self.user1, context={'request': request})
        self.assertEqual(serializer.data['phone_number'], '+12345678901')

        # Serialize user2 with admin's request context
        serializer = UserSerializer(self.user2, context={'request': request})
        self.assertEqual(serializer.data['phone_number'], '+19876543210')

    def test_unauthenticated_user_sees_fully_masked_phone(self):
        """Test that unauthenticated users see fully masked phone numbers."""
        from core.api.serializers import UserSerializer
        from django.contrib.auth.models import AnonymousUser

        # Create a mock request without authentication
        request = self.client.get('/').wsgi_request
        request.user = AnonymousUser()

        # Serialize user1 without authentication
        serializer = UserSerializer(self.user1, context={'request': request})

        # Should be fully masked
        self.assertEqual(serializer.data['phone_number'], '***-***-****')


@pytest.mark.django_db
class TestEmailValidation(TestCase):
    """Test email validation in EmailService."""

    def setUp(self):
        """Set up test."""
        cache.clear()

    def test_valid_email_passes_validation(self):
        """Test that valid emails pass validation."""
        self.assertTrue(EmailService.validate_email('user@example.com'))
        self.assertTrue(EmailService.validate_email('test.user+tag@domain.co.uk'))

    def test_invalid_email_fails_validation(self):
        """Test that invalid emails fail validation."""
        self.assertFalse(EmailService.validate_email('not-an-email'))
        self.assertFalse(EmailService.validate_email('missing@domain'))
        self.assertFalse(EmailService.validate_email('@nodomain.com'))
        self.assertFalse(EmailService.validate_email('spaces in@email.com'))

    def test_send_email_rejects_invalid_address(self):
        """Test that send_email rejects invalid email addresses."""
        result = EmailService.send_email(
            recipient_email='invalid-email',
            subject='Test',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        self.assertFalse(result)


@pytest.mark.django_db
class TestEmailRateLimiting(TestCase):
    """Test email rate limiting."""

    def setUp(self):
        """Set up test."""
        cache.clear()

    def test_email_rate_limit_allows_within_limit(self):
        """Test that emails within rate limit are allowed."""
        email = 'test@example.com'

        # First email should pass
        self.assertTrue(EmailService.check_rate_limit(email))

        # Up to 10 emails should pass (default limit)
        for i in range(9):
            self.assertTrue(EmailService.check_rate_limit(email))

    def test_email_rate_limit_blocks_after_limit(self):
        """Test that emails are blocked after exceeding rate limit."""
        email = 'test@example.com'

        # Send 10 emails (the limit)
        for i in range(10):
            self.assertTrue(EmailService.check_rate_limit(email))

        # 11th email should be blocked
        self.assertFalse(EmailService.check_rate_limit(email))

    def test_email_rate_limit_is_per_recipient(self):
        """Test that rate limiting is per recipient."""
        email1 = 'user1@example.com'
        email2 = 'user2@example.com'

        # Send 10 emails to email1
        for i in range(10):
            self.assertTrue(EmailService.check_rate_limit(email1))

        # email1 should be blocked
        self.assertFalse(EmailService.check_rate_limit(email1))

        # But email2 should still work
        self.assertTrue(EmailService.check_rate_limit(email2))

    def test_send_email_respects_rate_limit(self):
        """Test that send_email respects rate limiting."""
        email = 'test@example.com'

        # Send 10 valid emails (should all succeed or fail for other reasons)
        for i in range(10):
            result = EmailService.send_email(
                recipient_email=email,
                subject=f'Test {i}',
                template_name='discussion_invite',
                context={'recipient_name': 'Test'},
            )
            # Note: This might fail due to template issues, but not rate limiting

        # 11th email should fail due to rate limiting
        result = EmailService.send_email(
            recipient_email=email,
            subject='Test 11',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        self.assertFalse(result)

    def test_email_rate_limit_cache_expiry(self):
        """Test that rate limit cache expires correctly."""
        email = 'test@example.com'

        # Fill up the rate limit
        for i in range(10):
            EmailService.check_rate_limit(email)

        # Should be blocked now
        self.assertFalse(EmailService.check_rate_limit(email))

        # Clear cache (simulating expiry)
        cache.delete(f'email_rate_limit:{email}')

        # Should work again
        self.assertTrue(EmailService.check_rate_limit(email))


@pytest.mark.django_db
class TestDataProtectionIntegration(TestCase):
    """Integration tests for data protection features."""

    def setUp(self):
        """Set up test."""
        cache.clear()
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="testuser",
            phone_number="+12345678901",
        )

    def test_phone_masking_in_serializer_context(self):
        """Test phone number masking works with serializer context."""
        from core.api.serializers import UserSerializer

        # Without request context
        serializer = UserSerializer(self.user)
        # Should be fully masked without request context
        self.assertIn('***', serializer.data['phone_number'])

        # With authenticated request context
        self.client.force_authenticate(user=self.user)
        request = self.client.get('/').wsgi_request
        request.user = self.user

        serializer = UserSerializer(self.user, context={'request': request})
        # User should see their own full number
        self.assertEqual(serializer.data['phone_number'], '+12345678901')

    def test_email_validation_with_rate_limiting(self):
        """Test that both email validation and rate limiting work together."""
        # Invalid email should fail validation before rate limiting
        for i in range(12):
            result = EmailService.send_email(
                recipient_email='invalid-email',
                subject='Test',
                template_name='discussion_invite',
                context={'recipient_name': 'Test'},
            )
            self.assertFalse(result)

        # All should fail due to validation, not rate limiting
        # So a valid email should still work
        result = EmailService.check_rate_limit('valid@example.com')
        self.assertTrue(result)
