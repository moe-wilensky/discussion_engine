"""
Phone-based registration service for user authentication.

Handles phone number verification via SMS with time-limited codes.
"""

import secrets
import uuid
from datetime import timedelta
from typing import Optional, Tuple

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from phonenumber_field.phonenumber import PhoneNumber
import phonenumbers

from core.models import User


class PhoneVerificationService:
    """
    Handle phone number verification via SMS.

    Manages verification code generation, storage, validation, and
    duplicate phone number detection.
    """

    # Cache key prefixes
    CODE_PREFIX = "verification_code:"
    PHONE_PREFIX = "verification_phone:"
    RATE_LIMIT_PREFIX = "verification_rate:"

    # Constants
    CODE_LENGTH = 6
    CODE_EXPIRY_MINUTES = 10
    RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour
    MAX_REQUESTS_PER_WINDOW = 3

    @classmethod
    def send_verification_code(cls, phone_number: str) -> Tuple[str, bool, str]:
        """
        Generate and send verification code to phone number.

        Args:
            phone_number: E.164 format phone number (e.g., '+12345678900')

        Returns:
            Tuple of (verification_id, success, message)

        Raises:
            ValidationError: If phone number is invalid or rate limited
        """
        # Validate phone number format
        try:
            parsed_phone = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed_phone):
                raise ValidationError("Invalid phone number")

            # Normalize to E.164 format
            phone_number = phonenumbers.format_number(
                parsed_phone, phonenumbers.PhoneNumberFormat.E164
            )
        except phonenumbers.NumberParseException:
            raise ValidationError("Invalid phone number format")

        # Check rate limiting
        if not cls._check_rate_limit(phone_number):
            raise ValidationError(
                "Too many verification requests. Please try again later."
            )

        # Check if phone already registered
        if User.objects.filter(phone_number=phone_number).exists():
            raise ValidationError("Phone number already registered")

        # Generate verification code
        code = cls._generate_code()
        verification_id = str(uuid.uuid4())

        # Store in cache
        code_key = f"{cls.CODE_PREFIX}{verification_id}"
        phone_key = f"{cls.PHONE_PREFIX}{verification_id}"

        expiry_seconds = cls.CODE_EXPIRY_MINUTES * 60
        cache.set(code_key, code, timeout=expiry_seconds)
        cache.set(phone_key, phone_number, timeout=expiry_seconds)

        # Update rate limit counter
        cls._increment_rate_limit(phone_number)

        # Send SMS (delegated to Celery task)
        from core.tasks import send_verification_sms

        send_verification_sms.delay(phone_number, code)

        return verification_id, True, "Verification code sent"

    @classmethod
    def verify_code(
        cls, verification_id: str, code: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verify the submitted code against stored value.

        Args:
            verification_id: UUID from send_verification_code
            code: 6-digit code from user

        Returns:
            Tuple of (is_valid, message, phone_number)
        """
        code_key = f"{cls.CODE_PREFIX}{verification_id}"
        phone_key = f"{cls.PHONE_PREFIX}{verification_id}"

        # Retrieve from cache
        stored_code = cache.get(code_key)
        phone_number = cache.get(phone_key)

        if not stored_code or not phone_number:
            return False, "Verification code expired or invalid", None

        # Check code match
        if stored_code != code:
            return False, "Invalid verification code", None

        # Code is valid - delete from cache to prevent reuse
        cache.delete(code_key)
        cache.delete(phone_key)

        return True, "Phone number verified", phone_number

    @classmethod
    def _generate_code(cls) -> str:
        """Generate a cryptographically secure 6-digit verification code."""
        # Use secrets.randbelow to generate a random 6-digit number
        # This ensures cryptographically secure random generation
        code_number = secrets.randbelow(1000000)
        # Format with leading zeros to ensure 6 digits
        return f"{code_number:06d}"

    @classmethod
    def _check_rate_limit(cls, phone_number: str) -> bool:
        """
        Check if phone number is within rate limit.

        Args:
            phone_number: Phone number to check

        Returns:
            True if within rate limit, False if exceeded
        """
        rate_key = f"{cls.RATE_LIMIT_PREFIX}{phone_number}"
        current_count = cache.get(rate_key, 0)

        return current_count < cls.MAX_REQUESTS_PER_WINDOW

    @classmethod
    def _increment_rate_limit(cls, phone_number: str) -> None:
        """Increment rate limit counter for phone number."""
        rate_key = f"{cls.RATE_LIMIT_PREFIX}{phone_number}"
        current_count = cache.get(rate_key, 0)
        cache.set(rate_key, current_count + 1, timeout=cls.RATE_LIMIT_WINDOW_SECONDS)
