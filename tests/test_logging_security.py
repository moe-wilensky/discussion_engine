"""
Tests for logging security.

Ensures no sensitive data (codes, tokens, full phone numbers) is logged.
"""

import pytest
import logging
import io
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.services.email_service import EmailService
from core.tasks import send_verification_sms

User = get_user_model()


class LogCapture:
    """Helper class to capture log output."""

    def __init__(self):
        self.records = []
        self.handler = logging.Handler()
        self.handler.emit = self._emit

    def _emit(self, record):
        self.records.append(record)

    def get_messages(self):
        """Get all log messages as strings."""
        return [record.getMessage() for record in self.records]

    def attach_to_logger(self, logger_name):
        """Attach this capture to a logger."""
        logger = logging.getLogger(logger_name)
        logger.addHandler(self.handler)
        return logger

    def detach_from_logger(self, logger_name):
        """Detach from logger."""
        logger = logging.getLogger(logger_name)
        logger.removeHandler(self.handler)


@pytest.mark.django_db
class TestLoggingSecurity(TestCase):
    """Test that sensitive data is not logged."""

    def setUp(self):
        """Set up test."""
        cache.clear()
        self.log_capture = LogCapture()

    def tearDown(self):
        """Clean up."""
        self.log_capture.detach_from_logger('core.services.email_service')
        self.log_capture.detach_from_logger('core.tasks')

    def test_email_service_does_not_log_full_email(self):
        """Test that email service masks email addresses in logs."""
        self.log_capture.attach_to_logger('core.services.email_service')

        # Try to send an email
        EmailService.send_email(
            recipient_email='sensitive@example.com',
            subject='Test',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        messages = self.log_capture.get_messages()

        # Check that full email is not in logs
        for message in messages:
            self.assertNotIn('sensitive@example.com', message)
            # Should contain masked version
            if 'email' in message.lower():
                self.assertIn('***', message)

    def test_email_service_does_not_log_on_invalid_email(self):
        """Test that invalid email addresses are masked in error logs."""
        self.log_capture.attach_to_logger('core.services.email_service')

        # Try invalid email
        EmailService.validate_email('invalid-email@')

        messages = self.log_capture.get_messages()

        # Should not contain full invalid email
        for message in messages:
            if 'invalid' in message.lower():
                # Should be masked
                self.assertIn('***', message)

    def test_sms_task_does_not_log_phone_or_code(self):
        """Test that SMS task does not log phone numbers or verification codes."""
        self.log_capture.attach_to_logger('core.tasks')

        phone = '+12345678901'
        code = '123456'

        # Call the task
        send_verification_sms(phone, code)

        messages = self.log_capture.get_messages()

        # Check that neither full phone nor code is logged
        for message in messages:
            self.assertNotIn(phone, message, "Full phone number found in logs!")
            self.assertNotIn(code, message, "Verification code found in logs!")

            # Should contain masked version if phone is mentioned
            if 'sms' in message.lower():
                # Should show last 4 digits only
                self.assertIn('8901', message)
                self.assertIn('***', message)

    def test_email_rate_limit_does_not_log_full_email(self):
        """Test that rate limiting logs masked email addresses."""
        self.log_capture.attach_to_logger('core.services.email_service')

        email = 'ratelimit@example.com'

        # Hit rate limit
        for i in range(11):
            EmailService.check_rate_limit(email)

        messages = self.log_capture.get_messages()

        # Check that full email is not in logs
        for message in messages:
            self.assertNotIn('ratelimit@example.com', message)
            # Rate limit warnings should contain masked email
            if 'rate limit' in message.lower():
                self.assertIn('***', message)

    def test_no_sensitive_patterns_in_logs(self):
        """Test that common sensitive patterns are not logged."""
        self.log_capture.attach_to_logger('core.services.email_service')
        self.log_capture.attach_to_logger('core.tasks')

        # Try various operations that might log
        EmailService.send_email(
            recipient_email='test@example.com',
            subject='Test',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        send_verification_sms('+12345678901', '654321')

        messages = self.log_capture.get_messages()

        # Patterns that should NEVER appear in logs
        sensitive_patterns = [
            r'\+1\d{10}',  # Full US phone numbers
            r'\d{6}',  # 6-digit codes
            r'password',  # Passwords
            r'token',  # Tokens
            r'secret',  # Secrets
        ]

        import re
        for message in messages:
            # Check for 6-digit codes (verification codes)
            if re.search(r'\b\d{6}\b', message):
                self.fail(f"6-digit code found in log: {message}")

            # Check for full phone numbers (should be masked)
            if re.search(r'\+1\d{10}', message):
                self.fail(f"Full phone number found in log: {message}")


@pytest.mark.django_db
class TestLoggingLevels(TestCase):
    """Test that logging uses appropriate levels."""

    def setUp(self):
        """Set up test."""
        cache.clear()
        self.log_capture = LogCapture()

    def tearDown(self):
        """Clean up."""
        self.log_capture.detach_from_logger('core.services.email_service')

    def test_email_success_uses_info_level(self):
        """Test that successful email sends use INFO level."""
        self.log_capture.attach_to_logger('core.services.email_service')

        # This will fail due to missing template, but check the logging level
        EmailService.send_email(
            recipient_email='test@example.com',
            subject='Test',
            template_name='discussion_invite',
            context={'recipient_name': 'Test'},
        )

        # Check for appropriate logging levels
        for record in self.log_capture.records:
            if 'success' in record.getMessage().lower():
                self.assertEqual(record.levelno, logging.INFO)

    def test_email_errors_use_error_level(self):
        """Test that email errors use ERROR level."""
        self.log_capture.attach_to_logger('core.services.email_service')

        # Invalid email should trigger error log
        EmailService.send_email(
            recipient_email='invalid',
            subject='Test',
            template_name='test',
            context={},
        )

        # Should have error-level logs
        error_logs = [r for r in self.log_capture.records if r.levelno >= logging.ERROR]
        self.assertGreater(len(error_logs), 0, "Should have error-level logs for invalid email")

    def test_rate_limit_uses_warning_level(self):
        """Test that rate limiting uses WARNING level."""
        self.log_capture.attach_to_logger('core.services.email_service')

        email = 'test@example.com'

        # Hit rate limit
        for i in range(11):
            EmailService.check_rate_limit(email)

        # Should have warning-level logs
        warning_logs = [r for r in self.log_capture.records if r.levelno == logging.WARNING]
        self.assertGreater(len(warning_logs), 0, "Should have warning-level logs for rate limiting")


@pytest.mark.django_db
class TestPhoneNumberMaskingInLogs(TestCase):
    """Test that phone numbers are properly masked in all logs."""

    def test_phone_masking_shows_last_4_digits_only(self):
        """Test that phone number masking shows only last 4 digits."""
        log_capture = LogCapture()
        log_capture.attach_to_logger('core.tasks')

        phone = '+19876543210'
        code = '999999'

        send_verification_sms(phone, code)

        messages = log_capture.get_messages()

        # Find messages about SMS
        sms_messages = [m for m in messages if 'sms' in m.lower()]

        self.assertGreater(len(sms_messages), 0, "Should have SMS-related log messages")

        for message in sms_messages:
            # Should contain last 4 digits
            self.assertIn('3210', message, "Should show last 4 digits")

            # Should NOT contain full phone number
            self.assertNotIn('+19876543210', message, "Should not show full phone")
            self.assertNotIn('9876543210', message, "Should not show phone without +")

            # Should contain masking
            self.assertIn('***', message, "Should contain *** masking")

            # Should NOT contain verification code
            self.assertNotIn('999999', message, "Should not contain verification code")

        log_capture.detach_from_logger('core.tasks')
