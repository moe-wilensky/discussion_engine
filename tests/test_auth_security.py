"""
Tests for authentication security.

Tests SMS verification code security, JWT token blacklisting,
and error message sanitization.
"""

import pytest
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from core.auth.registration import PhoneVerificationService
from core.models import PlatformConfig

User = get_user_model()


@pytest.mark.django_db
class TestSMSCodeSecurity:
    """Test SMS verification code security."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear cache before each test."""
        cache.clear()

        # Create platform config
        PlatformConfig.objects.get_or_create(
            pk=1,
            defaults={
                "max_discussion_participants": 10,
                "responses_to_unlock_invites": 5,
                "new_user_platform_invites": 3,
                "new_user_discussion_invites": 3,
            },
        )

    def test_sms_codes_are_six_digits(self):
        """Test that SMS verification codes are exactly 6 digits."""
        codes = []
        for _ in range(10):
            code = PhoneVerificationService._generate_code()
            assert len(code) == 6
            assert code.isdigit()
            codes.append(code)

    def test_sms_codes_are_unique(self):
        """Test that SMS verification codes are unique (generate 100 codes)."""
        codes = set()
        for _ in range(100):
            code = PhoneVerificationService._generate_code()
            codes.add(code)

        # With cryptographically secure random, we should have very high uniqueness
        # Allow for a small collision rate (< 5% for 100 codes)
        assert len(codes) >= 95, f"Only {len(codes)} unique codes out of 100"

    def test_sms_codes_have_good_distribution(self):
        """Test that SMS codes don't show obvious patterns."""
        codes = []
        for _ in range(100):
            code = PhoneVerificationService._generate_code()
            codes.append(code)

        # Check that codes span the full range
        int_codes = [int(code) for code in codes]
        min_code = min(int_codes)
        max_code = max(int_codes)

        # Should span a reasonable range (at least 50% of possible space)
        # Range is 0-999999, so 50% would be 500000
        assert (max_code - min_code) > 500000, "Codes don't span sufficient range"

    def test_sms_codes_are_formatted_with_leading_zeros(self):
        """Test that SMS codes maintain leading zeros."""
        # Generate many codes and check that some have leading zeros
        codes = []
        for _ in range(100):
            code = PhoneVerificationService._generate_code()
            codes.append(code)
            assert len(code) == 6, f"Code {code} is not 6 digits"

        # Statistically, about 10% of codes should start with 0
        codes_with_leading_zero = [c for c in codes if c.startswith("0")]
        assert len(codes_with_leading_zero) > 0, "No codes with leading zeros found"


@pytest.mark.django_db
class TestJWTBlacklisting:
    """Test JWT token blacklisting."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.client = APIClient()

        # Create platform config
        PlatformConfig.objects.get_or_create(
            pk=1,
            defaults={
                "max_discussion_participants": 10,
                "responses_to_unlock_invites": 5,
                "new_user_platform_invites": 3,
                "new_user_discussion_invites": 3,
            },
        )

        # Create a test user
        self.user = User.objects.create_user(
            username="testuser", phone_number="+11234567890"
        )

    def test_refresh_token_is_blacklisted_after_rotation(self):
        """Test that old refresh tokens are blacklisted after rotation."""
        # Generate initial tokens
        refresh = RefreshToken.for_user(self.user)
        old_refresh_token = str(refresh)
        access_token = str(refresh.access_token)

        # Use the refresh token to get new tokens (this should blacklist the old one)
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": old_refresh_token},
            format="json",
        )

        assert response.status_code == 200
        new_tokens = response.json()
        assert "access" in new_tokens
        assert "refresh" in new_tokens

        # Try to use the old refresh token again - should be rejected
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": old_refresh_token},
            format="json",
        )

        # Should fail because the old token is blacklisted
        assert response.status_code == 401

    def test_blacklisted_tokens_are_stored(self):
        """Test that blacklisted tokens are stored in the database."""
        # Clear any existing blacklisted tokens
        BlacklistedToken.objects.all().delete()
        OutstandingToken.objects.all().delete()

        # Generate tokens
        refresh = RefreshToken.for_user(self.user)
        old_refresh_token = str(refresh)

        # Rotate tokens
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": old_refresh_token},
            format="json",
        )

        assert response.status_code == 200

        # Check that a token was blacklisted
        blacklisted_count = BlacklistedToken.objects.count()
        assert blacklisted_count > 0, "No tokens were blacklisted"

    def test_access_token_works_after_refresh_rotation(self):
        """Test that new access tokens work after refresh token rotation."""
        # Generate initial tokens
        refresh = RefreshToken.for_user(self.user)
        old_refresh_token = str(refresh)

        # Rotate tokens
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": old_refresh_token},
            format="json",
        )

        assert response.status_code == 200
        new_tokens = response.json()
        new_access_token = new_tokens["access"]

        # Use the new access token to access a protected endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access_token}")
        response = self.client.get("/api/invites/me/")

        # Should work
        assert response.status_code == 200


@pytest.mark.django_db
class TestErrorMessageSanitization:
    """Test that error messages don't expose internal details."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.client = APIClient()

        # Create platform config
        PlatformConfig.objects.get_or_create(
            pk=1,
            defaults={
                "max_discussion_participants": 10,
                "responses_to_unlock_invites": 5,
                "new_user_platform_invites": 3,
                "new_user_discussion_invites": 3,
            },
        )

    def test_registration_error_is_sanitized(self):
        """Test that registration errors don't expose stack traces."""
        # Try to register with invalid data to trigger an error
        response = self.client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": "invalid-id",
                "code": "123456",
                "username": "testuser",
            },
            format="json",
        )

        assert response.status_code == 400
        error_data = response.json()

        # Error can be in different formats (validation error or generic error)
        # Both are safe - we just need to ensure no internal details are exposed
        error_msg = str(error_data).lower()

        # Should not contain stack traces or internal details
        assert "traceback" not in error_msg
        assert "exception" not in error_msg
        assert "django" not in error_msg
        assert "line " not in error_msg
        assert "file " not in error_msg
        assert ".py" not in error_msg

    def test_discussion_creation_error_is_sanitized(self):
        """Test that discussion creation errors don't expose internals."""
        # Create a user and authenticate
        user = User.objects.create_user(
            username="testuser", phone_number="+11234567890"
        )
        self.client.force_authenticate(user=user)

        # Try to create discussion with invalid data
        response = self.client.post(
            "/api/discussions/",
            {
                "headline": "Test",
                "details": "Test details",
                # Missing required parameters to trigger error
            },
            format="json",
        )

        if response.status_code == 400:
            error_data = response.json()
            if "error" in error_data:
                error_msg = error_data["error"].lower()

                # Should not contain stack traces or internal details
                assert "traceback" not in error_msg
                assert ".py" not in error_msg

    def test_error_messages_are_user_friendly(self):
        """Test that error messages are user-friendly and generic."""
        # Test various error scenarios and ensure messages are appropriate

        # Invalid verification code
        response = self.client.post(
            "/api/auth/register/verify/",
            {
                "verification_id": "00000000-0000-0000-0000-000000000000",
                "code": "000000",
                "username": "testuser",
            },
            format="json",
        )

        assert response.status_code == 400
        error_data = response.json()
        assert "error" in error_data

        # Error should be descriptive but not reveal system internals
        error_msg = error_data["error"]
        assert len(error_msg) < 200  # Reasonably short
        assert len(error_msg) > 10  # But not too short to be useless
